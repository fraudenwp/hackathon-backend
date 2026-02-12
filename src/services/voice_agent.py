"""
Voice AI Agent - Using LiveKit Agents framework with FAL.AI
"""

import asyncio
from typing import Dict, Optional

from livekit import rtc
from livekit.agents import Agent, AgentSession
from livekit.plugins.silero import VAD

from src.services.livekit_service import livekit_service
from src.services.plugins import FalSTT, FalLLM, FalTTS
from src.utils.logger import get_logger, log_error

logger = get_logger(__name__)


class FalAssistant(Agent):
    """Custom AI Assistant using FAL.AI plugins"""

    def __init__(self, system_prompt: str = "You are a helpful AI assistant.") -> None:
        super().__init__(instructions=system_prompt)


class VoiceAgent:
    """AI agent using LiveKit Agents framework with FAL.AI"""

    def __init__(
        self,
        room_name: str,
        agent_name: str = "AI Assistant",
        system_prompt: Optional[str] = None,
    ):
        self.room_name = room_name
        self.agent_name = agent_name
        self.system_prompt = system_prompt or "You are a helpful AI assistant."

        self.room: Optional[rtc.Room] = None
        self.session: Optional[AgentSession] = None
        self.is_running = False
        self._disconnected_event: Optional[asyncio.Event] = None

    async def start(self) -> None:
        """Start the agent and join the room"""
        try:
            logger.info("Starting voice agent", room=self.room_name)

            # Generate token for agent
            token = await livekit_service.generate_token(
                room_name=self.room_name,
                participant_identity=f"agent-{self.room_name}",
                participant_name=self.agent_name,
                metadata={"is_agent": True, "type": "voice_ai"},
            )

            # Create room instance
            self.room = rtc.Room()
            self._disconnected_event = asyncio.Event()

            # Listen for disconnect to unblock wait
            @self.room.on("disconnected")
            def _on_disconnected(*args):
                logger.info("Room disconnected", room=self.room_name)
                self._disconnected_event.set()

            # Connect to room
            from src.constants.env import LIVEKIT_WS_URL

            await self.room.connect(LIVEKIT_WS_URL, token)

            # Create agent session with FAL.AI plugins
            self.session = AgentSession(
                stt=FalSTT(model="freya-stt-v1"),
                llm=FalLLM(model="meta-llama/llama-3.1-70b-instruct", temperature=0.7),
                tts=FalTTS(voice="alloy", speed=1.0),
                vad=VAD.load(),
            )

            # Start session with custom assistant
            await self.session.start(
                room=self.room, agent=FalAssistant(system_prompt=self.system_prompt)
            )

            self.is_running = True
            logger.info("Voice agent started successfully", room=self.room_name)

        except Exception as e:
            log_error(logger, "Failed to start voice agent", e, room=self.room_name)
            raise

    async def wait_until_done(self) -> None:
        """Block until the room disconnects or agent is stopped"""
        if self._disconnected_event:
            await self._disconnected_event.wait()

    async def stop(self) -> None:
        """Stop the agent and leave the room"""
        try:
            logger.info("Stopping voice agent", room=self.room_name)

            self.is_running = False

            if self._disconnected_event:
                self._disconnected_event.set()

            if self.session:
                await self.session.aclose()
                self.session = None

            if self.room:
                await self.room.disconnect()
                self.room = None

            logger.info("Voice agent stopped", room=self.room_name)

        except Exception as e:
            log_error(logger, "Error stopping voice agent", e, room=self.room_name)


# Active agents dictionary
active_agents: Dict[str, VoiceAgent] = {}


async def start_agent(
    room_name: str, system_prompt: Optional[str] = None
) -> VoiceAgent:
    """Start a voice agent in a room"""
    if room_name in active_agents:
        raise ValueError(f"Agent already running in room {room_name}")

    agent = VoiceAgent(room_name, system_prompt=system_prompt)
    await agent.start()
    active_agents[room_name] = agent

    return agent


async def stop_agent(room_name: str) -> None:
    """Stop a voice agent in a room"""
    if room_name not in active_agents:
        raise ValueError(f"No agent running in room {room_name}")

    agent = active_agents[room_name]
    await agent.stop()
    del active_agents[room_name]


def get_agent(room_name: str) -> Optional[VoiceAgent]:
    """Get active agent for a room"""
    return active_agents.get(room_name)
