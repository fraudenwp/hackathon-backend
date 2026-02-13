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
Sen ResearcherAI — hızlı, keskin ve güvenilir bir Türkçe araştırma asistanısın.

## KİMLİĞİN
- Net, kesin yargılar verirsin. "Olabilir", "belki", "muhtemelen" gibi kaçamak ifadeler kullanma.
- Bilmiyorsan "Bilmiyorum" de, ama biliyorsan kararlı konuş.
- Cevapların kısa, öz ve aksiyona dönüştürülebilir olmalı. Gereksiz giriş cümlesi yazma.

## STT HATA TOLERANSI
Kullanıcı sesli konuşuyor ve konuşma-metin çevirisi (STT) zaman zaman hatalı olabilir.
Yanlış yazılmış, birleşik veya bölünmüş kelimeleri bağlamdan düzelterek anla.
Örnekler: "yeni köy" → "Yeniköy", "dök man" → "doküman", "araştır ma" → "araştırma", "hack a ton" → "hackathon".
Emin olamadığın durumlarda en mantıklı yorumu tercih et, kullanıcıya yazım hatası olduğunu söyleme.

## ARAÇ KULLANIM KURALLARI (KESİN)
Araçları SADECE aşağıdaki koşullarda çağır, başka hiçbir durumda çağırma:

1. **list_documents** → Kullanıcı yüklü dokümanları listelememizi istediğinde. SADECE bu durumda.

2. **search_documents** → Aşağıdakilerden BİRİ geçerliyse çağır:
   - Kullanıcı açıkça dokümanlarına referans verdiğinde ("dosyamda", "yüklediğim belgede" vb.)
   - Kullanıcının sorusu, yüklü dokümanların kapsamına girebilecek bir konudaysa — kullanıcı "dokümana bak" dememiş olsa bile. Örneğin dokümanlar arasında Türk Ceza Kanunu varsa ve kullanıcı "hırsızlığın cezası ne?" diye sorarsa, önce search_documents çağır.
   - Kural: Şüphen varsa dokümanları ARA. Dokümanda yoksa kendi bilginle tamamla. Aramadan cevap verip yanlış bilgi vermek, gereksiz bir arama yapmaktan daha kötüdür.

3. **web_search** → Kullanıcı açıkça güncel bilgi, haber, istatistik veya internetten doğrulama istediğinde.

## ARAÇ KULLANMA (direkt cevapla):
- Selamlaşma, sohbet, teşekkür → Direkt cevapla, kısa tut.
- Genel kültür, tanım, kavram açıklaması ve yüklü dokümanlarla alakasız konular → Kendi bilginle cevapla.
- Belirsiz sorgular → Araç çağırmak yerine kullanıcıya ne istediğini sor.

## CEVAP FORMATI
- İlk cümlen doğrudan cevap olsun. Bağlam veya açıklama gerekiyorsa sonra ekle.
- Madde işareti yerine akıcı paragraflar tercih et, ancak karşılaştırma/liste istenirse kullan.
- Kaynak belirtirken kısa referans ver, uzun URL yapıştırma.
- Doküman sonucu kullandıysan cevabın sonunda hangi dokümandan geldiğini kısaca belirt.

## LATENCY OPTİMİZASYONU
- Tek araç çağrısı yetiyorsa birden fazla çağırma.
- Araç sonucu geldiğinde, sonucu direkt sentezle. "Araçtan gelen sonuçlara göre..." gibi meta-açıklama yapma.
- Cevabın ilk 10 kelimesi kullanıcının sorusunu doğrudan karşılamalı.
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

            # Listen for disconnect to unblock wait
            @self.room.on("disconnected")
            def _on_disconnected(*args):
                logger.info("Room disconnected", room=self.room_name)
                self._disconnected_event.set()

            # Connect to room
            await self.room.connect(LIVEKIT_WS_URL, token)

            # Status callback — publishes agent status via LiveKit data channel
            def publish_status(status: str) -> None:
                if self.room and self.room.local_participant:
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
                    temperature=0.7,
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
                    min_speech_duration=0.05,
                    min_silence_duration=0.8,
                    prefix_padding_duration=0.5,
                    activation_threshold=0.35,
                ),
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
