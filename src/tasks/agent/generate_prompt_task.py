"""Agent system prompt generation background task"""

from src.crud.agent import get_agent, update_agent
from src.models.database import db as database
from src.services.fal_ai import fal_ai_service
from src.tasks.taskiq_setup import broker
from src.utils.logger import logger

PROMPT_GENERATION_SYSTEM = """\
Sen bir sesli AI asistan için system prompt oluşturan aracısın.
Bu asistan SESLI konuşma ile çalışıyor (STT + TTS). Kullanıcı mikrofon ile konuşuyor, asistan sesli yanıt veriyor.

Kullanıcı sana asistanın adını ve ne yapmasını istediğini açıklayacak.
Sen de buna uygun, etkili bir Türkçe system prompt oluşturacaksın.

Kurallar:
- Prompt Türkçe olmalı
- Asistanın uzmanlık alanını ve görevini net tanımla
- ASLA "kendini tanıt" veya "hoş geldiniz mesajı ver" gibi talimatlar ekleme
- Asistan kullanıcının ilk mesajını BEKLEMELİ, kendiliğinden konuşmaya başlamamalı
- Yanıtlar KISA ve KONUŞMA DİLİNDE olmalı (sesli asistan, uzun metin değil)
- Bir seferde en fazla 2-3 cümle söylemeli
- Liste, madde işareti veya markdown KULLANMAMALI (sesle okunacak)
- STT hata toleransı: Kullanıcı sesli konuştuğu için yazım/telaffuz hataları olabilir, niyeti anlamaya çalış
- Araçlar: Gerektiğinde search_documents (döküman arama), list_documents (döküman listeleme), web_search (internet arama) kullanabilir
- Sadece system prompt metnini yaz, başka açıklama veya yorum ekleme
"""


@broker.task
async def generate_agent_prompt(agent_id: str):
    """Generate a system prompt for an agent using LLM"""
    logger.info("Starting prompt generation", agent_id=agent_id)

    async with database.get_session_context() as db:
        agent = await get_agent(db, agent_id)
        if not agent:
            logger.error("Agent not found", agent_id=agent_id)
            return {"success": False, "error": "Agent not found"}

    try:
        messages = [
            {"role": "system", "content": PROMPT_GENERATION_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Asistan adı: {agent.name}\n"
                    f"Açıklama: {agent.description}\n\n"
                    "Bu asistan için etkili bir system prompt oluştur."
                ),
            },
        ]

        system_prompt = await fal_ai_service.generate_llm_response(
            messages=messages,
            model="meta-llama/llama-3.1-70b-instruct",
            temperature=0.7,
            max_tokens=800,
        )

        async with database.get_session_context() as db:
            await update_agent(
                db, agent_id, system_prompt=system_prompt.strip(), status="ready"
            )

        logger.info("Prompt generation completed", agent_id=agent_id)
        return {"success": True, "agent_id": agent_id}

    except Exception as e:
        logger.error("Prompt generation failed", agent_id=agent_id, error=str(e))
        async with database.get_session_context() as db:
            await update_agent(db, agent_id, status="failed")
        raise
