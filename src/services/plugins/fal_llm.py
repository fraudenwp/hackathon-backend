"""FAL.AI LLM Plugin for LiveKit Agents"""

from typing import List
from livekit.agents import llm
from livekit.agents.llm import LLM, ChatContext, ChatMessage, ChatRole

from src.services.fal_ai import fal_ai_service
from src.utils.logger import get_logger, log_error

logger = get_logger(__name__)


class FalLLM(LLM):
    """FAL.AI LLM plugin for LiveKit Agents"""

    def __init__(self, model: str = "meta-llama/llama-3.1-70b-instruct", temperature: float = 0.7):
        super().__init__()
        self.model = model
        self.temperature = temperature

    async def chat(
        self,
        *,
        chat_ctx: ChatContext,
        fnc_ctx: llm.FunctionContext | None = None,
        temperature: float | None = None,
        n: int = 1,
    ) -> "llm.LLMStream":
        """Generate chat response"""
        try:
            # Convert ChatContext to FAL.AI format
            messages = []
            for msg in chat_ctx.messages:
                role = "user" if msg.role == ChatRole.USER else "assistant"
                if msg.role == ChatRole.SYSTEM:
                    role = "system"

                messages.append({
                    "role": role,
                    "content": msg.content
                })

            # Call FAL.AI LLM
            result = await fal_ai_service.generate_llm_response(
                messages=messages,
                model=self.model,
                temperature=temperature or self.temperature,
                max_tokens=150,
            )

            response_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Return as stream (even though it's not streaming)
            return FalLLMStream(response_text)

        except Exception as e:
            log_error(logger, "FAL LLM chat failed", e)
            return FalLLMStream("")


class FalLLMStream(llm.LLMStream):
    """Stream wrapper for FAL.AI responses"""

    def __init__(self, text: str):
        super().__init__(llm=None, chat_ctx=None)
        self._text = text
        self._done = False

    async def aclose(self) -> None:
        pass

    async def __anext__(self) -> llm.ChatChunk:
        if self._done:
            raise StopAsyncIteration

        self._done = True
        return llm.ChatChunk(
            choices=[
                llm.Choice(
                    delta=llm.ChoiceDelta(
                        role=ChatRole.ASSISTANT,
                        content=self._text
                    )
                )
            ]
        )
