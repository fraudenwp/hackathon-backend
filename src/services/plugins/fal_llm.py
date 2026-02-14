"""FAL.AI LLM Plugin for LiveKit Agents — with tool calling support"""

from __future__ import annotations

import asyncio
import json as _json
import re
from typing import Any, Callable, Optional

from livekit.agents import llm
from livekit.agents.llm import LLM, ChatContext, ChatChunk, ChoiceDelta, LLMStream, Tool
from livekit.agents.types import (
    DEFAULT_API_CONNECT_OPTIONS,
    APIConnectOptions,
    NOT_GIVEN,
    NotGivenOr,
)

from src.services.fal_ai import fal_ai_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

MAX_TOOL_ROUNDS = 2

# Regex to strip markdown artifacts that TTS would read aloud
_MD_STRIP = re.compile(r"\*{1,2}|#{1,6}\s?|`{1,3}|^-\s|^\d+\.\s", re.MULTILINE)

# Tool name → human-readable status (for frontend indicator)
TOOL_STATUS_MAP: dict[str, str] = {
    "web_search": "Searching the web...",
    "search_documents": "Searching documents...",
    "list_documents": "Listing documents...",
    "news_search": "Searching news...",
    "wikipedia_search": "Searching Wikipedia...",
    "generate_visual": "Generating visual...",
}

# Tool name → spoken filler (what the agent SAYS via TTS before running the tool)
TOOL_FILLER_MAP: dict[str, str] = {
    "web_search": "Bir saniye, internetten araştırıyorum.",
    "search_documents": "Dökümanlarınızı kontrol ediyorum.",
    "list_documents": "Dökümanlarınıza bakıyorum.",
    "news_search": "Haberlere bakıyorum.",
    "wikipedia_search": "Wikipedia'ya bakıyorum.",
    "generate_visual": "Bir görsel hazırlıyorum, ekrana bakın.",
}


class FalLLM(LLM):
    """FAL.AI LLM plugin for LiveKit Agents"""

    def __init__(
        self,
        model: str = "openai/gpt-4o-mini",
        temperature: float = 0.7,
        user_id: Optional[str] = None,
        doc_ids: Optional[list[str]] = None,
        room_name: Optional[str] = None,
        on_status: Optional[Callable[[str], Any]] = None,
    ):
        super().__init__()
        self._model = model
        self._temperature = temperature
        self._user_id = user_id
        self._doc_ids = doc_ids
        self._room_name = room_name
        self._on_status = on_status

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        tools: list[Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[llm.ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> LLMStream:
        return FalLLMStream(
            llm=self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            model=self._model,
            temperature=self._temperature,
            user_id=self._user_id,
            doc_ids=self._doc_ids,
            room_name=self._room_name,
            on_status=self._on_status,
        )


class FalLLMStream(LLMStream):
    """Stream wrapper for FAL.AI responses with tool calling"""

    def __init__(
        self,
        *,
        llm: FalLLM,
        chat_ctx: ChatContext,
        tools: list[Tool],
        conn_options: APIConnectOptions,
        model: str,
        temperature: float,
        user_id: Optional[str] = None,
        doc_ids: Optional[list[str]] = None,
        room_name: Optional[str] = None,
        on_status: Optional[Callable[[str], Any]] = None,
    ) -> None:
        super().__init__(
            llm=llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options
        )
        self._model = model
        self._temperature = temperature
        self._user_id = user_id
        self._doc_ids = doc_ids
        self._room_name = room_name
        self._on_status = on_status

    def _publish_status(self, status: str) -> None:
        """Send status update to frontend via callback"""
        if self._on_status:
            try:
                self._on_status(status)
            except Exception:
                pass

    def _publish_visual(self, image_url: str) -> None:
        """Send generated visual URL to frontend via status callback (JSON payload)"""
        if self._on_status:
            try:
                # Prefix with __VISUAL__: so frontend can distinguish from status
                self._on_status(f"__VISUAL__:{image_url}")
            except Exception:
                pass

    def _inject_rag_context(self, messages: list[dict]) -> list[dict]:
        """Search user's documents and inject relevant context into messages"""
        if not self._user_id:
            return messages

        try:
            from src.services.rag_service import rag_service

            if not rag_service.has_documents(self._user_id):
                return messages

            # Get the last user message as query
            user_query = ""
            for msg in reversed(messages):
                if msg["role"] == "user" and msg["content"]:
                    user_query = msg["content"]
                    break

            if not user_query:
                return messages

            self._publish_status("Searching documents...")
            results = rag_service.search(self._user_id, user_query, k=5, doc_ids=self._doc_ids)
            if not results:
                return messages

            context_str = "\n---\n".join(r["text"] for r in results)

            rag_msg = {
                "role": "system",
                "content": (
                    f"Kullanicinin yukledigi dokumanlardan ilgili bolumler:\n\n{context_str}\n\n"
                    "Bu bilgileri kullanarak soruyu yanitla. "
                    "Eger bilgi dokumanlarda yoksa bunu belirt."
                ),
            }

            for i, msg in enumerate(messages):
                if msg["role"] == "system":
                    messages.insert(i + 1, rag_msg)
                    return messages

            messages.insert(0, rag_msg)
            return messages

        except Exception as e:
            logger.warning("RAG context injection failed", error=str(e))
            return messages

    async def _save_message(self, role: str, content: str) -> None:
        """Save a message to the database (fire-and-forget)"""
        if not self._room_name or not content.strip():
            return
        try:
            from src.models.database import db as database
            from src.crud.voice_conversation import get_conversation_by_room, create_message

            async with database.get_session_context() as db:
                conv = await get_conversation_by_room(db, self._room_name)
                if not conv:
                    return
                await create_message(
                    db=db,
                    conversation_id=conv.id,
                    participant_identity="user" if role == "user" else "agent",
                    participant_name="User" if role == "user" else "AI Assistant",
                    message_type="transcript" if role == "user" else "ai_response",
                    content=content.strip(),
                )
        except Exception as e:
            logger.warning("Failed to save message", error=str(e))

    async def _run(self) -> None:
        """Stream tokens with tool call support."""
        from src.services.tools import tool_registry

        messages = []
        for msg in self._chat_ctx.items:
            if not hasattr(msg, "role"):
                continue
            messages.append({"role": msg.role, "content": msg.text_content or ""})

        # Save user's last message (fire-and-forget — don't block LLM)
        user_text = ""
        for msg in reversed(messages):
            if msg["role"] == "user" and msg["content"]:
                user_text = msg["content"]
                break
        if user_text:
            asyncio.create_task(self._save_message("user", user_text))

        # Inject RAG context (skip for very short messages like greetings)
        self._publish_status("Thinking...")
        if len(user_text.split()) >= 2:
            messages = self._inject_rag_context(messages)

        # Get tool definitions
        tool_defs = tool_registry.to_openai_functions() or None

        request_id = "fal-response"
        full_response = ""  # Accumulate full AI response for saving
        used_tools = False

        for _round in range(MAX_TOOL_ROUNDS):
            # Accumulate tool_calls from streamed chunks
            tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, arguments}
            filler_sent = False
            if used_tools:
                self._publish_status("Analyzing results...")
            else:
                self._publish_status("Thinking...")

            # Normal: voice response. After tools: needs room to synthesize results.
            tokens = 4096 if used_tools else 1024

            async for chunk in fal_ai_service.generate_llm_response_stream_raw(
                messages=messages,
                model=self._model,
                temperature=self._temperature,
                max_tokens=tokens,
                tools=tool_defs,
                tool_choice="auto" if tool_defs else None,
            ):
                delta = chunk.get("choices", [{}])[0].get("delta", {})

                # Stream content tokens to TTS (strip markdown so TTS doesn't read ** etc.)
                if delta.get("content"):
                    full_response += delta["content"]
                    clean = _MD_STRIP.sub("", delta["content"])
                    if clean:
                        self._event_ch.send_nowait(
                            ChatChunk(
                                id=request_id,
                                delta=ChoiceDelta(role="assistant", content=clean),
                            )
                        )

                # Accumulate tool call chunks
                if delta.get("tool_calls"):
                    for tc in delta["tool_calls"]:
                        idx = tc["index"]
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": tc.get("id", ""),
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": "",
                            }
                        if tc.get("id"):
                            tool_calls_acc[idx]["id"] = tc["id"]
                        if tc.get("function", {}).get("name"):
                            tool_calls_acc[idx]["name"] = tc["function"]["name"]
                            # Speak filler immediately when tool name is known
                            if not filler_sent:
                                filler = TOOL_FILLER_MAP.get(
                                    tc["function"]["name"], "Bir saniye bakayım."
                                )
                                self._event_ch.send_nowait(
                                    ChatChunk(
                                        id=request_id,
                                        delta=ChoiceDelta(role="assistant", content=filler),
                                    )
                                )
                                self._publish_status("Calling tools...")
                                filler_sent = True
                        if tc.get("function", {}).get("arguments"):
                            tool_calls_acc[idx]["arguments"] += tc["function"]["arguments"]

            # If no tool calls, we're done
            if not tool_calls_acc:
                break

            # Execute tool calls
            used_tools = True
            logger.info("Executing tool calls", count=len(tool_calls_acc))

            # Add assistant message with tool_calls to messages
            assistant_msg = {"role": "assistant", "content": None, "tool_calls": []}
            for idx in sorted(tool_calls_acc.keys()):
                tc = tool_calls_acc[idx]
                assistant_msg["tool_calls"].append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                })
            messages.append(assistant_msg)

            # Execute each tool and add results
            for idx in sorted(tool_calls_acc.keys()):
                tc = tool_calls_acc[idx]
                try:
                    args = _json.loads(tc["arguments"]) if tc["arguments"] else {}
                except _json.JSONDecodeError:
                    args = {}

                # Inject user_id and doc_ids for tools that need it
                if self._user_id:
                    args["user_id"] = self._user_id
                if self._doc_ids:
                    args["doc_ids"] = self._doc_ids

                status_msg = TOOL_STATUS_MAP.get(tc["name"], f"Running {tc['name']}...")
                self._publish_status(status_msg)

                result = await tool_registry.execute(tc["name"], **args)
                logger.info(
                    "Tool executed",
                    tool=tc["name"],
                    result_len=len(result),
                    result_preview=result[:300],
                )

                # Intercept visual URL and broadcast to frontend
                if result.startswith("__VISUAL_URL__:"):
                    image_url = result[len("__VISUAL_URL__:"):]
                    self._publish_visual(image_url)
                    # Give the LLM a clean result
                    result = "Görsel başarıyla oluşturuldu ve kullanıcının ekranında gösteriliyor. Görseli açıklamaya devam et."

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

            # Continue loop — next iteration will stream with tool results
            self._publish_status("Preparing answer...")
            # Disable tools for the follow-up to get a text response
            tool_defs = None

        # Save AI response to DB
        if full_response:
            await self._save_message("assistant", full_response)

        # Signal that LLM processing is done (TTS may still be playing)
        self._publish_status("_done")
