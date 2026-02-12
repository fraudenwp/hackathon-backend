"""FAL.AI STT Plugin for LiveKit Agents"""

import io
import wave

from livekit.agents.stt import (
    STT,
    STTCapabilities,
    SpeechEvent,
    SpeechEventType,
    SpeechData,
)
from livekit.agents.types import (
    DEFAULT_API_CONNECT_OPTIONS,
    APIConnectOptions,
    NOT_GIVEN,
    NotGivenOr,
)
from livekit.agents.utils.audio import AudioBuffer

from src.services.fal_ai import fal_ai_service
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1) -> bytes:
    """Convert raw PCM int16 data to WAV format"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # int16 = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


class FalSTT(STT):
    """FAL.AI Speech-to-Text plugin for LiveKit Agents"""

    def __init__(self, model: str = "freya-stt-v1"):
        super().__init__(
            capabilities=STTCapabilities(streaming=False, interim_results=False)
        )
        self._model_name = model

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> SpeechEvent:
        """Recognize speech from audio buffer"""
        # Convert AudioBuffer to raw PCM bytes and get sample rate
        if isinstance(buffer, list):
            pcm_data = b"".join(frame.data.tobytes() for frame in buffer)
            sample_rate = buffer[0].sample_rate if buffer else 24000
            channels = buffer[0].num_channels if buffer else 1
        else:
            pcm_data = buffer.data.tobytes()
            sample_rate = buffer.sample_rate
            channels = buffer.num_channels

        # Wrap PCM in WAV header so API accepts it
        wav_data = _pcm_to_wav(pcm_data, sample_rate, channels)

        # Call FAL.AI STT
        lang = language if isinstance(language, str) else "tr"
        result = await fal_ai_service.transcribe_audio(
            audio=wav_data,
            model=self._model_name,
            language=lang,
        )

        text = result.get("text", "")

        return SpeechEvent(
            type=SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[SpeechData(text=text, language=lang)],
        )
