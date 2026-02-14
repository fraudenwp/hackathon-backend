"""
Voice AI Agent - Using LiveKit Agents framework with FAL.AI via OpenAI-compatible clients
"""

import asyncio
import json as _json
from typing import Dict, Optional

import openai as oai
from livekit import api, rtc
from livekit.agents import Agent, AgentSession
from livekit.plugins import openai as lk_openai
from livekit.plugins.silero import VAD

from src.constants.env import FAL_API_KEY, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_WS_URL
from src.services.latency_tracker import latency_tracker
from src.services.plugins import FalLLM
from src.utils.logger import get_logger, log_error

logger = get_logger(__name__)

FAL_BASE_URL = "https://fal.run"
FAL_STT_APP = "freya-mypsdi253hbk/freya-stt"
FAL_TTS_APP = "freya-mypsdi253hbk/freya-tts"

_fal_headers = {"Authorization": f"Key {FAL_API_KEY}"}

_stt_client = oai.AsyncClient(
    api_key="stub",
    base_url=f"{FAL_BASE_URL}/{FAL_STT_APP}",
    default_headers=_fal_headers,
)

_tts_client = oai.AsyncClient(
    api_key="stub",
    base_url=f"{FAL_BASE_URL}/{FAL_TTS_APP}",
    default_headers=_fal_headers,
)


_DEFAULT_SYSTEM_PROMPT = """\
You are ResearcherAI — a student's personal research & learning companion.
**ALWAYS RESPOND IN TURKISH (Türkçe). This is the highest-priority, non-negotiable rule.**

IDENTITY: Curious, patient educator. Simplify complex topics, spark curiosity, use analogies.

TOOL USAGE (be proactive):
- search_documents → Search student's uploaded notes/books. Use when topic might match their coursework. When in doubt, search first.
- generate_visual → Create diagrams/infographics for visual concepts (science, math, timelines, anatomy, processes). Use generously — visuals boost learning 60%.
- web_search → Search web when uncertain or need current data. Never guess — search instead.
- news_search → For current events, breaking news queries.
- wikipedia_search → For encyclopedic topics (history, science, biography).
- list_documents → Only when user asks "what files do I have?"

RESPONSE RULES:
- Voice-based: use natural conversational Turkish, NO markdown/bullets/lists
- Start with a direct answer, keep sentences short and clear
- Synthesize tool results naturally — never say "according to the tool..."
- Be confident — avoid "maybe", "possibly", "probably"
- Correct STT errors from context silently (e.g. "dök man" → "doküman")
- Don't call multiple tools when one suffices
"""

class FalAssistant(Agent):
    """Custom AI Assistant using FAL.AI plugins"""

    def __init__(self, system_prompt: str | None = None) -> None:
        super().__init__(instructions=system_prompt or _DEFAULT_SYSTEM_PROMPT)


class VoiceAgent:
    """AI agent using LiveKit Agents framework with FAL.AI"""

    def __init__(
        self,
        room_name: str,
        agent_name: str = "AI Assistant",
        system_prompt: Optional[str] = None,
        user_id: Optional[str] = None,
        doc_ids: Optional[list[str]] = None,
    ):
        self.room_name = room_name
        self.agent_name = agent_name
        self.system_prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT
        self.user_id = user_id
        self.doc_ids = doc_ids

        self.room: Optional[rtc.Room] = None
        self.session: Optional[AgentSession] = None
        self.is_running = False
        self._disconnected_event: Optional[asyncio.Event] = None

    async def start(self) -> None:
        """Start the agent and join the room"""
        try:
            logger.info("Starting voice agent", room=self.room_name)

            # Generate token for agent (with agent kind so isAgent=true on client)
            token_obj = api.AccessToken(
                LIVEKIT_API_KEY, LIVEKIT_API_SECRET
            )
            token_obj.with_identity(f"agent-{self.room_name}")
            token_obj.with_name(self.agent_name)
            token_obj.with_kind("agent")
            token_obj.with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=self.room_name,
                    can_publish=True,
                    can_subscribe=True,
                    agent=True,
                )
            )
            token = token_obj.to_jwt()

            # Create room instance
            self.room = rtc.Room()
            self._disconnected_event = asyncio.Event()

            # Track participants
            self._participant_identities: set[str] = set()

            @self.room.on("participant_connected")
            def _on_participant_connected(participant, *args):
                self._participant_identities.add(participant.identity)
                logger.info("Participant connected", room=self.room_name, identity=participant.identity)

            # Listen for disconnect — end conversation in DB
            @self.room.on("disconnected")
            def _on_disconnected(*args):
                logger.info("Room disconnected", room=self.room_name)
                asyncio.ensure_future(self._end_conversation())
                self._disconnected_event.set()

            # Connect to room
            await self.room.connect(LIVEKIT_WS_URL, token)

            # Status callback — publishes agent status via LiveKit data channel
            def publish_status(status: str) -> None:
                if not (self.room and self.room.local_participant):
                    return
                # Visual image URL — send on dedicated topic
                if status.startswith("__VISUAL__:"):
                    image_url = status[len("__VISUAL__:"):]
                    payload = _json.dumps({"type": "agent_visual", "url": image_url}).encode()
                    asyncio.ensure_future(
                        self.room.local_participant.publish_data(payload, topic="agent_visual")
                    )
                    return
                # Visual loading signal — tell frontend to show loading placeholder
                if status == "__VISUAL_LOADING__":
                    payload = _json.dumps({"type": "agent_visual_loading"}).encode()
                    asyncio.ensure_future(
                        self.room.local_participant.publish_data(payload, topic="agent_visual")
                    )
                    return
                payload = _json.dumps({"type": "agent_status", "status": status}).encode()
                asyncio.ensure_future(
                    self.room.local_participant.publish_data(payload, topic="agent_status")
                )

            # Create agent session — STT & TTS via LiveKit OpenAI plugin with fal.ai base_url
            self.session = AgentSession(
                stt=lk_openai.STT(
                    client=_stt_client,
                    model="freya-stt-v1",
                    language="tr",
                ),
                llm=FalLLM(
                    model="openai/gpt-4o-mini",
                    temperature=0.5,
                    user_id=self.user_id,
                    doc_ids=self.doc_ids,
                    room_name=self.room_name,
                    on_status=publish_status,
                ),
                tts=lk_openai.TTS(
                    client=_tts_client,
                    model="freya-tts-v1",
                    voice="alloy",
                ),
                vad=VAD.load(
                    min_speech_duration=0.2,
                    min_silence_duration=0.35,
                    prefix_padding_duration=0.2,
                    activation_threshold=0.55,
                ),
                # Echo/feedback loop prevention — allow interruptions but
                # require real speech (not just echo picked up by mic)
                allow_interruptions=True,
                min_interruption_duration=0.5,
                min_interruption_words=2,
                false_interruption_timeout=0.8,
                resume_false_interruption=True,
            )

            # Start session with custom assistant
            await self.session.start(
                room=self.room, agent=FalAssistant(system_prompt=self.system_prompt)
            )

            # -- Latency tracking events --
            @self.session.on("user_state_changed")
            def _on_user_state_changed(ev):
                # User stopped speaking → mark speech end
                if ev.old_state == "speaking" and ev.new_state == "listening":
                    latency_tracker.on_user_speech_end(self.room_name)

            @self.session.on("agent_state_changed")
            def _on_agent_state_changed(ev):
                # Agent started speaking → measure latency
                if ev.new_state == "speaking":
                    latency_tracker.on_agent_speech_start(self.room_name)

            self.is_running = True
            logger.info("Voice agent started successfully", room=self.room_name)

        except Exception as e:
            log_error(logger, "Failed to start voice agent", e, room=self.room_name)
            raise

    async def _end_conversation(self) -> None:
        """End conversation in DB with duration and participant count"""
        try:
            from src.models.database import db as database
            from src.crud.voice_conversation import get_conversation_by_room, end_conversation

            async with database.get_session_context() as db:
                conv = await get_conversation_by_room(db, self.room_name)
                if conv and conv.status != "ended":
                    participant_count = len(getattr(self, "_participant_identities", set()))
                    await end_conversation(db, conv.id, participant_count=participant_count)
                    logger.info(
                        "Conversation ended",
                        room=self.room_name,
                        participant_count=participant_count,
                    )
        except Exception as e:
            log_error(logger, "Failed to end conversation", e, room=self.room_name)

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
    room_name: str,
    system_prompt: Optional[str] = None,
    user_id: Optional[str] = None,
    doc_ids: Optional[list[str]] = None,
) -> VoiceAgent:
    """Start a voice agent in a room"""
    if room_name in active_agents:
        raise ValueError(f"Agent already running in room {room_name}")

    agent = VoiceAgent(room_name, system_prompt=system_prompt, user_id=user_id, doc_ids=doc_ids)
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
