"""FAL.AI LLM Plugin for LiveKit Agents"""

from __future__ import annotations

from typing import Any

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


class FalLLM(LLM):
    """FAL.AI LLM plugin for LiveKit Agents"""

    def __init__(
        self, model: str = "meta-llama/llama-3.1-70b-instruct", temperature: float = 0.7
    ):
        super().__init__()
        self._model = model
        self._temperature = temperature

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
        )


class FalLLMStream(LLMStream):
    """Stream wrapper for FAL.AI responses"""

    def __init__(
        self,
        *,
        llm: FalLLM,
        chat_ctx: ChatContext,
        tools: list[Tool],
        conn_options: APIConnectOptions,
        model: str,
        temperature: float,
    ) -> None:
        super().__init__(
            llm=llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options
        )
        self._model = model
        self._temperature = temperature

    async def _run(self) -> None:
        """Stream tokens from FAL.AI to minimize time-to-first-byte."""
        messages = []
        for msg in self._chat_ctx.items:
            if not hasattr(msg, "role"):
                continue
            messages.append({"role": msg.role, "content": msg.text_content or ""})

        request_id = "fal-response"

        # Stream token by token — each delta goes to TTS immediately
        async for token in fal_ai_service.generate_llm_response_stream(
            messages=messages,
            model=self._model,
            temperature=self._temperature,
            max_tokens=150,
        ):
            self._event_ch.send_nowait(
                ChatChunk(
                    id=request_id,
                    delta=ChoiceDelta(role="assistant", content=token),
                )
            )
