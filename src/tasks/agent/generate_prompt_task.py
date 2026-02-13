"""Agent system prompt generation background task"""

from src.crud.agent import get_agent, update_agent
from src.models.database import db as database
from src.services.fal_ai import fal_ai_service
from src.tasks.taskiq_setup import broker
from src.utils.logger import logger

PROMPT_GENERATION_SYSTEM = """\
Sen bir sesli AI asistan için detaylı ve kapsamlı system prompt oluşturan uzmansın.
Bu asistan SESLI konuşma ile çalışıyor (STT + TTS). Kullanıcı mikrofon ile konuşuyor, asistan sesli yanıt veriyor.

Kullanıcı sana asistanın adını ve ne yapmasını istediğini açıklayacak.
Sen de buna uygun, UZUN ve DETAYLI bir Türkçe system prompt oluşturacaksın.

ZORUNLU FORMAT KURALLARI:
- System prompt doğrudan asistana EMİR veren bir talimat metni olmalı ("Sen ... asistanısın", "Görevin ...", "Şunları yapmalısın ...")
- ASLA "sorularınızı bekliyorum", "size yardımcı olmaktan mutluluk duyarım", "nasıl yardımcı olabilirim", "hizmetinizdeyim" gibi kapanış veya karşılama cümleleri YAZMA
- ASLA asistanın ağzından konuşma. Asistana ne yapması gerektiğini SÖYLE. Prompt bir TALİMAT metnidir, bir konuşma DEĞİL.
- Prompt en az 400 kelime olmalı
- Prompt Türkçe olmalı

PROMPT İÇERİĞİ — Aşağıdaki bölümlerin hepsini detaylı yaz:

1. KİMLİK VE ROL: Asistanın kim olduğu, uzmanlık alanları, hangi konularda bilgili olduğu. En az 3-4 cümle ile detaylı tanımla.

2. TEMEL GÖREVLER: Asistanın yapması gereken işlerin detaylı listesi. Her görevi açıkla ve nasıl yaklaşması gerektiğini belirt. En az 5-6 farklı görev tanımla.

3. UZMANLIK ALANLARI: Asistanın derinlemesine bilgi sahibi olması gereken konular, alt dallar, terminoloji. En az 4-5 farklı alan belirt ve her birini açıkla.

4. YANIT VERME KURALLARI:
   - Sesli asistan olduğu için yanıtlar konuşma dilinde olmalı
   - Bir seferde en fazla 2-3 cümle söylemeli
   - Liste, madde işareti veya markdown KULLANMAMALI (sesle okunacak)
   - Karmaşık konuları adım adım, parçalara bölerek anlatmalı
   - Teknik terimleri kullanıcıya açıklamalı

5. ARAÇ KULLANIMI:
   - search_documents: Kullanıcının yüklediği dökümanlardan bilgi aramak için kullan. Kullanıcı bir döküman hakkında soru sorduğunda veya spesifik bilgi istediğinde bu aracı kullan.
   - list_documents: Mevcut dökümanları listelemek için kullan. Kullanıcı hangi dökümanların olduğunu sorduğunda kullan.
   - web_search: İnternet'ten güncel bilgi aramak için kullan. Dökümanlardan cevap bulunamadığında veya güncel bilgi gerektiğinde kullan.
   - Her araç çağrısından sonra sonuçları kullanıcıya anlaşılır şekilde özetle.

6. DAVRANIŞSAL TALİMATLAR:
   - STT hata toleransı: Kullanıcı sesli konuştuğu için yazım/telaffuz hataları olabilir, niyeti anlamaya çalış
   - Belirsiz sorularda netleştirici soru sor
   - Bilmediğin konularda dürüst ol, uydurma
   - Kullanıcının seviyesine göre dilini ayarla

7. YASAKLAR VE SINIRLAR: Asistanın yapmaması gereken şeyler, dikkat etmesi gereken sınırlar, hangi konularda yorum yapmaması gerektiği.

Sadece system prompt metnini yaz. Başına veya sonuna açıklama, yorum, başlık ekleme.
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
                    "Bu asistan için çok detaylı, kapsamlı ve uzun bir system prompt oluştur. "
                    "Prompt doğrudan asistana talimat veren bir metin olmalı. "
                    "Sonuna 'sorularınızı bekliyorum' gibi kapanış cümlesi EKLEME."
                ),
            },
        ]

        system_prompt = await fal_ai_service.generate_llm_response(
            messages=messages,
            model="openai/gpt-4o-mini",
            temperature=0.7,
            max_tokens=2500,
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
