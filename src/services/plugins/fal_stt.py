"""FAL.AI STT Plugin for LiveKit Agents"""

from livekit.agents.stt import (
    STT,
    STTCapabilities,
    SpeechEvent,
    SpeechEventType,
    SpeechData,
)
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions, NOT_GIVEN, NotGivenOr
from livekit.agents.utils.audio import AudioBuffer

from src.services.fal_ai import fal_ai_service
from src.utils.logger import get_logger, log_error

logger = get_logger(__name__)


class FalSTT(STT):
    """FAL.AI Speech-to-Text plugin for LiveKit Agents"""

    def __init__(self, model: str = "freya-stt-v1"):
        super().__init__(capabilities=STTCapabilities(streaming=False, interim_results=False))
        self.model = model

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> SpeechEvent:
        """Recognize speech from audio buffer"""
        # Convert AudioBuffer (list[AudioFrame] | AudioFrame) to bytes
        if isinstance(buffer, list):
            audio_data = b"".join(frame.data.tobytes() for frame in buffer)
        else:
            audio_data = buffer.data.tobytes()

        # Call FAL.AI STT
        result = await fal_ai_service.transcribe_audio(
            audio=audio_data,
            model=self.model,
        )

        text = result.get("text", "")
        lang = language if isinstance(language, str) else "en"

        return SpeechEvent(
            type=SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[SpeechData(text=text, language=lang)],
        )
