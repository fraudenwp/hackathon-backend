"""FAL.AI TTS Plugin for LiveKit Agents"""

from __future__ import annotations

from livekit.agents.tts import TTS, TTSCapabilities, ChunkedStream
from livekit.agents.tts.tts import AudioEmitter
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

from src.services.fal_ai import fal_ai_service
from src.utils.logger import get_logger

logger = get_logger(__name__)

SAMPLE_RATE = 24000
NUM_CHANNELS = 1


class FalTTS(TTS):
    """FAL.AI Text-to-Speech plugin for LiveKit Agents"""

    def __init__(self, voice: str = "alloy", speed: float = 1.0):
        super().__init__(
            capabilities=TTSCapabilities(streaming=False),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
        )
        self._voice = voice
        self._speed = speed

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> ChunkedStream:
        return FalTTSChunkedStream(
            tts=self,
            input_text=text,
            conn_options=conn_options,
            voice=self._voice,
            speed=self._speed,
        )


class FalTTSChunkedStream(ChunkedStream):
    """Chunked TTS stream from FAL.AI"""

    def __init__(
        self,
        *,
        tts: FalTTS,
        input_text: str,
        conn_options: APIConnectOptions,
        voice: str,
        speed: float,
    ) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._voice = voice
        self._speed = speed

    async def _run(self, output_emitter: AudioEmitter) -> None:
        """Stream audio chunks from FAL.AI using AudioEmitter pattern."""
        output_emitter.initialize(
            request_id="fal-tts",
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            mime_type="audio/wav",
        )

        async for audio_chunk in fal_ai_service.synthesize_speech_stream(
            input=self.input_text,
            voice=self._voice,
            speed=self._speed,
            response_format="wav",
        ):
            if audio_chunk:
                output_emitter.push(audio_chunk)

        output_emitter.flush()
