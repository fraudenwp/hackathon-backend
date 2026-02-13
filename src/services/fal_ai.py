"""
Fal AI Service - LLM via OpenRouter on fal.ai
"""

from typing import Any, AsyncIterator, Dict, Optional

import httpx

from src.constants.env import FAL_API_KEY
from src.utils.logger import get_logger, log_error

logger = get_logger(__name__)


class FalAIService:
    """Service for fal.ai LLM endpoints"""

    BASE_URL = "https://fal.run"
    LLM_ENDPOINT = "openrouter/router/openai/v1/chat/completions"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or FAL_API_KEY
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=3.0, read=30.0),
            headers={
                "Authorization": f"Key {self.api_key}",
                "Content-Type": "application/json",
            },
            http2=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate_llm_response_stream_raw(
        self,
        messages: Optional[list] = None,
        model: Optional[str] = None,
        tools: Optional[list] = None,
        tool_choice: Optional[str | Dict] = None,
        **kwargs: Any,
    ) -> AsyncIterator[Dict]:
        """Streaming LLM — yields raw parsed SSE chunks (for tool call handling)."""
        import json as _json

        endpoint = f"{self.BASE_URL}/{self.LLM_ENDPOINT}"

        payload: Dict[str, Any] = {"stream": True, **kwargs}
        if messages is not None:
            payload["messages"] = messages
        if model is not None:
            payload["model"] = model
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

        try:
            async with self._client.stream("POST", endpoint, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    yield _json.loads(data)

        except httpx.HTTPError as e:
            log_error(
                logger,
                "LLM stream (raw) failed",
                e,
                endpoint=endpoint,
                status_code=getattr(e.response, "status_code", None),
            )
            raise

    async def generate_llm_response(
        self,
        messages: list,
            model: str = "openai/gpt-4o-mini",
        **kwargs: Any,
    ) -> str:
        """Non-streaming LLM call — returns complete response text."""
        endpoint = f"{self.BASE_URL}/{self.LLM_ENDPOINT}"

        payload: Dict[str, Any] = {
            "stream": False,
            "messages": messages,
            "model": model,
            **kwargs,
        }

        try:
            response = await self._client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

        except httpx.HTTPError as e:
            log_error(
                logger,
                "LLM response failed",
                e,
                endpoint=endpoint,
                status_code=getattr(e.response, "status_code", None),
            )
            raise


# Singleton instance
fal_ai_service = FalAIService()
