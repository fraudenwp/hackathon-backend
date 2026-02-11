"""FAL.AI TTS Plugin for LiveKit Agents"""

from livekit.agents import tts
from livekit.agents.tts import TTS, SynthesizedAudio

from src.services.fal_ai import fal_ai_service
from src.utils.logger import get_logger, log_error

logger = get_logger(__name__)


class FalTTS(TTS):
    """FAL.AI Text-to-Speech plugin for LiveKit Agents"""

    def __init__(self, voice: str = "alloy", speed: float = 1.0):
        super().__init__(streaming_supported=True, sample_rate=24000, num_channels=1)
        self.voice = voice
        self.speed = speed

    def synthesize(self, text: str) -> "FalTTSStream":
        """Synthesize text to speech"""
        return FalTTSStream(
            text=text,
            voice=self.voice,
            speed=self.speed,
            sample_rate=self._sample_rate,
            num_channels=self._num_channels,
        )


class FalTTSStream(tts.ChunkedStream):
    """Streaming TTS from FAL.AI"""

    def __init__(
        self,
        text: str,
        voice: str,
        speed: float,
        sample_rate: int,
        num_channels: int,
    ):
        super().__init__()
        self._text = text
        self._voice = voice
        self._speed = speed
        self._sample_rate = sample_rate
        self._num_channels = num_channels
        self._stream = None

    async def _run(self):
        """Stream audio chunks from FAL.AI"""
        try:
            # Get streaming audio from FAL.AI
            async for audio_chunk in fal_ai_service.synthesize_speech_stream(
                input=self._text,
                voice=self._voice,
                speed=self._speed,
                response_format="wav",
            ):
                if audio_chunk:
                    # Create audio frame
                    frame = tts.AudioFrame(
                        data=audio_chunk,
                        sample_rate=self._sample_rate,
                        num_channels=self._num_channels,
                        samples_per_channel=len(audio_chunk) // (2 * self._num_channels),
                    )
                    self._event_ch.send_nowait(
                        tts.SynthesizedAudio(
                            request_id="",
                            frame=frame,
                        )
                    )

        except Exception as e:
            log_error(logger, "FAL TTS streaming failed", e)

        finally:
            await self.aclose()
