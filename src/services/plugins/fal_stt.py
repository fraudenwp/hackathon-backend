"""
Streaming-emulated STT for fal.ai HTTP endpoint.

fal.ai's freya-stt doesn't support WebSocket streaming natively.
We emulate it using Silero VAD for speech boundary detection (same neural
network the pipeline uses) + periodic HTTP transcription for interim results.

Architecture:
  - Uses a Silero VAD stream internally for accurate speech detection
  - During speech: accumulates frames, sends periodic HTTP requests → INTERIM_TRANSCRIPT
  - On VAD END_OF_SPEECH: reuses fresh interim or sends final HTTP request → FINAL_TRANSCRIPT

This gives us BOTH Silero-grade accuracy AND sub-second transcription latency.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import httpx
import openai
from livekit import rtc
from livekit.agents import (
    DEFAULT_API_CONNECT_OPTIONS,
    APIConnectionError,
    APIConnectOptions,
    APITimeoutError,
    stt,
    utils,
    vad as vad_module,
)
from livekit.agents.types import NOT_GIVEN, NotGivenOr
from livekit.agents.utils import is_given

from src.utils.logger import get_logger

logger = get_logger(__name__)

# ── Tuning knobs ──────────────────────────────────────────────────────────────
# How often to fire an interim HTTP request while user is speaking
_CHUNK_INTERVAL = 1.0
# Minimum accumulated audio before first interim
_MIN_AUDIO_SECS = 0.4
# If last interim finished < this many seconds ago, reuse it as final
_FRESH_INTERIM_THRESHOLD = 1.2


def _frames_to_wav(frames: list[rtc.AudioFrame]) -> bytes:
    if not frames:
        return b""
    combined = rtc.combine_audio_frames(frames)
    return combined.to_wav_bytes()


def _audio_duration_secs(total_samples: int, sample_rate: int) -> float:
    return total_samples / sample_rate if sample_rate else 0.0


class FalSTT(stt.STT):
    """
    Streaming-emulated STT for fal.ai with Silero VAD speech boundaries.

    Requires a Silero VAD instance for accurate speech detection.
    Sends periodic interim HTTP requests during speech and uses
    fresh interim reuse to minimize finalization latency.
    """

    def __init__(
        self,
        *,
        client: openai.AsyncClient,
        model: str = "freya-stt-v1",
        language: str = "tr",
        vad: vad_module.VAD | None = None,
    ):
        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=True,
                interim_results=True,
            )
        )
        self._client = client
        self._model = model
        self._language = language
        self._vad = vad

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "fal.ai"

    async def _recognize_impl(
        self,
        buffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechEvent:
        lang = language if is_given(language) else self._language
        wav = rtc.combine_audio_frames(buffer).to_wav_bytes()
        try:
            resp = await self._client.audio.transcriptions.create(
                file=("file.wav", wav, "audio/wav"),
                model=self._model,
                language=lang,
                response_format="json",
                timeout=httpx.Timeout(20, connect=5),
            )
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[stt.SpeechData(text=resp.text, language=lang)],
            )
        except openai.APITimeoutError:
            raise APITimeoutError() from None
        except Exception as e:
            raise APIConnectionError() from e

    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> "FalSpeechStream":
        lang = language if is_given(language) else self._language
        return FalSpeechStream(
            stt=self, language=lang, conn_options=conn_options, vad=self._vad
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Speech stream — Silero VAD boundaries + periodic interim transcription
# ═══════════════════════════════════════════════════════════════════════════════

class FalSpeechStream(stt.RecognizeStream):
    """
    Uses Silero VAD internally for accurate speech boundary detection.
    Sends periodic HTTP interim requests during speech, and on
    END_OF_SPEECH either reuses a fresh interim or sends a final request.
    """

    def __init__(
        self,
        *,
        stt: FalSTT,
        language: str,
        conn_options: APIConnectOptions,
        vad: vad_module.VAD | None,
    ):
        super().__init__(stt=stt, conn_options=conn_options)
        self._fal_stt = stt
        self._language = language
        self._vad = vad

        self._last_interim_text: str = ""
        self._last_interim_time: float = 0.0

    async def _transcribe(
        self, frames: list[rtc.AudioFrame], timeout_s: float = 12
    ) -> str:
        wav = _frames_to_wav(frames)
        if not wav:
            return ""
        resp = await self._fal_stt._client.audio.transcriptions.create(
            file=("file.wav", wav, "audio/wav"),
            model=self._fal_stt._model,
            language=self._language,
            response_format="json",
            timeout=httpx.Timeout(timeout_s, connect=3),
        )
        return resp.text or ""

    async def _send_interim(self, frames: list[rtc.AudioFrame]) -> None:
        try:
            text = await self._transcribe(frames, timeout_s=10)
            if text:
                self._last_interim_text = text
                self._last_interim_time = time.monotonic()
                self._event_ch.send_nowait(
                    stt.SpeechEvent(
                        type=stt.SpeechEventType.INTERIM_TRANSCRIPT,
                        alternatives=[
                            stt.SpeechData(text=text, language=self._language)
                        ],
                    )
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("Interim STT request failed (non-fatal)", error=str(e))

    def _emit_final(self, text: str, total_samples: int, sample_rate: int) -> None:
        if text:
            self._event_ch.send_nowait(
                stt.SpeechEvent(
                    type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                    alternatives=[
                        stt.SpeechData(text=text, language=self._language)
                    ],
                )
            )
        duration = _audio_duration_secs(total_samples, sample_rate)
        self._event_ch.send_nowait(
            stt.SpeechEvent(
                type=stt.SpeechEventType.RECOGNITION_USAGE,
                alternatives=[],
                recognition_usage=stt.RecognitionUsage(audio_duration=duration),
            )
        )

    async def _run(self) -> None:
        if not self._vad:
            logger.error("FalSTT: No VAD provided, cannot detect speech boundaries")
            return

        vad_stream = self._vad.stream()

        # Shared state between tasks
        speech_frames: list[rtc.AudioFrame] = []
        speech_total_samples: int = 0
        sample_rate: int = 48000
        in_speech: bool = False
        interim_task: Optional[asyncio.Task] = None
        last_interim_send: float = time.monotonic()

        async def _forward_audio() -> None:
            """Forward audio frames to VAD + accumulate during speech."""
            nonlocal in_speech, speech_total_samples, sample_rate
            nonlocal interim_task, last_interim_send

            async for data in self._input_ch:
                if isinstance(data, self._FlushSentinel):
                    vad_stream.flush()
                    continue

                if not isinstance(data, rtc.AudioFrame):
                    continue

                # Push to VAD for speech detection
                vad_stream.push_frame(data)

                if data.sample_rate:
                    sample_rate = data.sample_rate

                # Accumulate frames during speech
                if in_speech:
                    speech_frames.append(data)
                    speech_total_samples += data.samples_per_channel

                    # Periodic interim transcription
                    now = time.monotonic()
                    audio_secs = _audio_duration_secs(speech_total_samples, sample_rate)
                    if (
                        now - last_interim_send >= _CHUNK_INTERVAL
                        and audio_secs >= _MIN_AUDIO_SECS
                        and (interim_task is None or interim_task.done())
                    ):
                        interim_task = asyncio.create_task(
                            self._send_interim(list(speech_frames))
                        )
                        last_interim_send = now

            vad_stream.end_input()

        async def _process_vad_events() -> None:
            """Listen to VAD events and manage speech lifecycle."""
            nonlocal in_speech, speech_total_samples, sample_rate
            nonlocal interim_task, last_interim_send

            async for event in vad_stream:
                if event.type == vad_module.VADEventType.START_OF_SPEECH:
                    in_speech = True
                    speech_frames.clear()
                    speech_total_samples = 0
                    self._last_interim_text = ""
                    self._last_interim_time = 0.0
                    last_interim_send = time.monotonic()
                    logger.debug("VAD: speech started")

                elif event.type == vad_module.VADEventType.END_OF_SPEECH:
                    in_speech = False
                    logger.debug(
                        "VAD: speech ended",
                        speech_dur=f"{event.speech_duration:.2f}s",
                    )

                    # Cancel any in-flight interim
                    if interim_task and not interim_task.done():
                        interim_task.cancel()
                        try:
                            await interim_task
                        except (asyncio.CancelledError, Exception):
                            pass

                    # Use VAD's frames (accurate boundaries with padding)
                    # Fall back to our accumulated frames if VAD frames empty
                    final_frames = (
                        event.frames if event.frames else list(speech_frames)
                    )

                    if not final_frames:
                        speech_frames.clear()
                        speech_total_samples = 0
                        continue

                    # Calculate actual sample count from final frames
                    final_samples = sum(f.samples_per_channel for f in final_frames)
                    if final_frames[0].sample_rate:
                        sample_rate = final_frames[0].sample_rate

                    # Decide: reuse fresh interim or send new request
                    now = time.monotonic()
                    time_since_interim = now - self._last_interim_time

                    if (
                        self._last_interim_text
                        and self._last_interim_time > 0
                        and time_since_interim < _FRESH_INTERIM_THRESHOLD
                    ):
                        final_text = self._last_interim_text
                        logger.debug(
                            "Reusing fresh interim as final",
                            text=final_text[:60],
                            age_ms=int(time_since_interim * 1000),
                        )
                    else:
                        try:
                            final_text = await self._transcribe(
                                final_frames, timeout_s=12
                            )
                        except Exception as e:
                            logger.warning("Final STT request failed", error=str(e))
                            final_text = self._last_interim_text

                    self._emit_final(final_text, final_samples, sample_rate)

                    # Reset for next utterance
                    speech_frames.clear()
                    speech_total_samples = 0
                    self._last_interim_text = ""
                    self._last_interim_time = 0.0
                    last_interim_send = time.monotonic()

        tasks = [
            asyncio.create_task(_forward_audio(), name="fal_stt_forward"),
            asyncio.create_task(_process_vad_events(), name="fal_stt_vad"),
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            await utils.aio.cancel_and_wait(*tasks)
            await vad_stream.aclose()
