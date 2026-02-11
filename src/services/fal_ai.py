"""
Fal AI Service - Generic API wrapper for 3 endpoints from llms.txt
"""

from typing import Any, AsyncIterator, Dict, Optional

import httpx

from src.constants.env import FAL_API_KEY
from src.utils.logger import get_logger, log_error

logger = get_logger(__name__)


class FalAIService:
    """Generic service for Fal AI API endpoints"""

    BASE_URL = "https://fal.run"
    STT_ENDPOINT = "freya-mypsdi253hbk/freya-stt/audio/transcriptions"
    TTS_ENDPOINT = "freya-mypsdi253hbk/freya-tts/stream"
    LLM_ENDPOINT = "openrouter/router/openai/v1/responses"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or FAL_API_KEY
        # Persistent client — reuses TCP connections (eliminates per-request TLS handshake)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={
                "Authorization": f"Key {self.api_key}",
                "Content-Type": "application/json",
            },
            http2=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transcribe_audio(self, **kwargs: Any) -> Dict[str, Any]:
        """STT: https://fal.run/freya-mypsdi253hbk/freya-stt/audio/transcriptions"""
        endpoint = f"{self.BASE_URL}/{self.STT_ENDPOINT}"

        try:
            response = await self._client.post(endpoint, json=kwargs)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            log_error(
                logger,
                "STT failed",
                e,
                endpoint=endpoint,
                status_code=getattr(e.response, "status_code", None),
            )
            raise

    async def synthesize_speech(
        self,
        input: str,
        voice: str = "alloy",
        response_format: str = "wav",
        speed: float = 1.0,
        **kwargs: Any,
    ) -> bytes:
        """TTS: https://fal.run/freya-mypsdi253hbk/freya-tts/stream"""
        endpoint = f"{self.BASE_URL}/{self.TTS_ENDPOINT}"

        try:
            payload = {
                "input": input,
                "voice": voice,
                "response_format": response_format,
                "speed": speed,
                **kwargs,
            }

            response = await self._client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.content

        except httpx.HTTPError as e:
            log_error(
                logger,
                "TTS failed",
                e,
                endpoint=endpoint,
                status_code=getattr(e.response, "status_code", None),
            )
            raise

    async def synthesize_speech_stream(
        self,
        input: str,
        voice: str = "alloy",
        response_format: str = "wav",
        speed: float = 1.0,
        chunk_size: int = 8192,
        **kwargs: Any,
    ) -> AsyncIterator[bytes]:
        """TTS Streaming: https://fal.run/freya-mypsdi253hbk/freya-tts/stream"""
        endpoint = f"{self.BASE_URL}/{self.TTS_ENDPOINT}"

        try:
            payload = {
                "input": input,
                "voice": voice,
                "response_format": response_format,
                "speed": speed,
                **kwargs,
            }

            async with self._client.stream(
                "POST", endpoint, json=payload
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    yield chunk

        except httpx.HTTPError as e:
            log_error(
                logger,
                "TTS stream failed",
                e,
                endpoint=endpoint,
                status_code=getattr(e.response, "status_code", None),
            )
            raise

    async def generate_llm_response(
        self,
        messages: Optional[list] = None,
        model: Optional[str] = None,
        tools: Optional[list] = None,
        tool_choice: Optional[str | Dict] = None,
        response_format: Optional[Dict] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """LLM: https://fal.run/openrouter/router/openai/v1/responses"""
        endpoint = f"{self.BASE_URL}/{self.LLM_ENDPOINT}"

        payload = {**kwargs}
        if messages is not None:
            payload["messages"] = messages
        if model is not None:
            payload["model"] = model
        if tools is not None:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if response_format is not None:
            payload["response_format"] = response_format

        try:
            response = await self._client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            log_error(
                logger,
                "LLM failed",
                e,
                endpoint=endpoint,
                status_code=getattr(e.response, "status_code", None),
            )
            raise

    async def generate_llm_response_stream(
        self,
        messages: Optional[list] = None,
        model: Optional[str] = None,
        tools: Optional[list] = None,
        tool_choice: Optional[str | Dict] = None,
        response_format: Optional[Dict] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Streaming LLM — yields SSE delta content tokens."""
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
        if response_format is not None:
            payload["response_format"] = response_format

        try:
            async with self._client.stream(
                "POST", endpoint, json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    chunk = _json.loads(data)
                    delta = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content")
                    )
                    if delta:
                        yield delta

        except httpx.HTTPError as e:
            log_error(
                logger,
                "LLM stream failed",
                e,
                endpoint=endpoint,
                status_code=getattr(e.response, "status_code", None),
            )
            raise


# Singleton instance
fal_ai_service = FalAIService()
