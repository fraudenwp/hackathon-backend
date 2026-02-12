"""
Fal AI Service - Uses fal_client for TTS, httpx for STT/LLM
"""

import asyncio
import os
from typing import Any, AsyncIterator, Dict, Optional

import fal_client
import httpx
import requests

from src.constants.env import FAL_API_KEY
from src.utils.logger import get_logger, log_error

logger = get_logger(__name__)

# fal_client reads FAL_KEY from environment
os.environ.setdefault("FAL_KEY", FAL_API_KEY)


def _on_queue_update(update):
    """Callback for fal_client queue updates."""
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            logger.debug(f"[TTS] {log['message']}")


class FalAIService:
    """Generic service for Fal AI API endpoints"""

    BASE_URL = "https://fal.run"
    STT_ENDPOINT = "freya-mypsdi253hbk/freya-stt"
    TTS_ENDPOINT = os.getenv("TTS_ENDPOINT", "freya-mypsdi253hbk/freya-tts")
    LLM_ENDPOINT = "openrouter/router/openai/v1/chat/completions"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or FAL_API_KEY
        self._auth_header = {"Authorization": f"Key {self.api_key}"}

        # JSON client for LLM endpoints and audio download
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0, read=60.0),
            headers={
                **self._auth_header,
                "Content-Type": "application/json",
            },
            http2=True,
        )

        # Separate client for downloading audio (no auth headers needed)
        self._download_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0, read=60.0),
            http2=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
        await self._download_client.aclose()

    # ── STT ──────────────────────────────────────────────────────────

    def _sync_transcribe(
        self, endpoint: str, audio: bytes, model: str, **kwargs: Any
    ) -> Dict[str, Any]:
        """Synchronous STT call using requests (run in thread)"""
        files = {"file": ("audio.wav", audio, "audio/wav")}
        data = {"model": model, **kwargs}
        resp = requests.post(
            endpoint,
            files=files,
            data=data,
            headers={"Authorization": f"Key {self.api_key}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    async def transcribe_audio(
        self, audio: bytes, model: str = "freya-stt-v1", language: str = "tr", **kwargs: Any
    ) -> Dict[str, Any]:
        """STT: POST to freya-stt/audio/transcriptions"""
        endpoint = f"{self.BASE_URL}/{self.STT_ENDPOINT}/audio/transcriptions"

        try:
            result = await asyncio.to_thread(
                self._sync_transcribe, endpoint, audio, model, language=language, **kwargs
            )
            return result

        except requests.HTTPError as e:
            log_error(
                logger,
                "STT failed",
                e,
                endpoint=endpoint,
                status_code=getattr(e.response, "status_code", None),
                audio_size=len(audio),
            )
            raise
        except Exception as e:
            log_error(
                logger,
                "STT failed",
                e,
                endpoint=endpoint,
            )
            raise

    # ── TTS (fal_client.subscribe) ───────────────────────────────────

    async def synthesize_speech(
        self,
        input: str,
        voice: str = "alloy",
        response_format: str = "wav",
        speed: float = 1.0,
        **kwargs: Any,
    ) -> bytes:
        """TTS using fal_client.subscribe + download audio from CDN URL"""
        try:
            # fal_client.subscribe is synchronous, run in thread
            result = await asyncio.to_thread(
                fal_client.subscribe,
                self.TTS_ENDPOINT,
                arguments={
                    "input": input,
                    "voice": voice,
                    "response_format": response_format,
                    "speed": speed,
                    **kwargs,
                },
                path="/generate",
                with_logs=True,
                on_queue_update=_on_queue_update,
            )

            audio_url = result["audio"]["url"]
            logger.info(
                f"TTS generated: inference={result.get('inference_time_ms')}ms, "
                f"duration={result.get('audio_duration_sec')}s"
            )

            # Download audio bytes from CDN
            response = await self._download_client.get(audio_url, follow_redirects=True)
            response.raise_for_status()
            return response.content

        except Exception as e:
            log_error(
                logger,
                "TTS failed",
                e,
                endpoint=self.TTS_ENDPOINT,
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
        """TTS Streaming: direct HTTP POST to /stream endpoint (low latency)"""
        endpoint = f"{self.BASE_URL}/{self.TTS_ENDPOINT}/stream"

        try:
            payload = {
                "input": input,
                "voice": voice,
                "response_format": response_format,
                "speed": speed,
                **kwargs,
            }

            async with self._client.stream("POST", endpoint, json=payload) as response:
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

    # ── LLM ──────────────────────────────────────────────────────────

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
            async with self._client.stream("POST", endpoint, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    chunk = _json.loads(data)
                    delta = (
                        chunk.get("choices", [{}])[0].get("delta", {}).get("content")
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
