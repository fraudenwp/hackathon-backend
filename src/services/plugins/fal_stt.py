"""FAL.AI STT Plugin for LiveKit Agents"""

from livekit.agents.stt import STT, SpeechEvent, SpeechEventType, SpeechData
from typing import Any
from src.services.fal_ai import fal_ai_service
from src.utils.logger import get_logger, log_error

logger = get_logger(__name__)


class FalSTT(STT):
    """FAL.AI Speech-to-Text plugin for LiveKit Agents"""

    def __init__(self, model: str = "freya-stt-v1"):
        super().__init__(streaming_supported=False)
        self.model = model

    async def recognize(
        self,
        buffer: Any,
        *,
        language: str | None = None,
    ) -> SpeechEvent:
        """Recognize speech from audio buffer"""
        try:
            # Convert AudioBuffer to bytes
            audio_data = buffer.data

            # Call FAL.AI STT
            result = await fal_ai_service.transcribe_audio(
                audio=audio_data,
                model=self.model,
            )

            text = result.get("text", "")

            return SpeechEvent(
                type=SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[SpeechData(text=text, language=language or "en")],
            )

        except Exception as e:
            log_error(logger, "FAL STT recognition failed", e)
            return SpeechEvent(
                type=SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[SpeechData(text="", language=language or "en")],
            )
