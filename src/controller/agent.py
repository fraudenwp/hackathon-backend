from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from sqlmodel.ext.asyncio.session import AsyncSession

from src.crud.auth import AuthCRUD
from src.crud import agent as agent_crud
from src.crud import voice_conversation as conv_crud
from src.services.fal_ai import fal_ai_service
from src.models.basemodels.agent import (
    AgentCreateRequest,
    AgentUpdateRequest,
    AgentResponse,
    AgentListResponse,
    AgentDocumentAssignRequest,
    AgentDocumentResponse,
    DocumentAgentAssignRequest,
)
from src.models.dependency import get_session
from src.models.sqlmodels.user import User
from src.tasks.agent.generate_prompt_task import generate_agent_prompt
from src.utils.logger import logger


class AgentController:
    tags = ["agent"]
    router = APIRouter(tags=tags)

    @router.post("/")
    async def create_agent(
        request: AgentCreateRequest,
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ) -> AgentResponse:
        """Create a new agent and trigger system prompt generation"""
        agent = await agent_crud.create_agent(
            db=db,
            user_id=current_user.id,
            name=request.name,
            description=request.description,
        )

        # Trigger prompt generation in background
        await generate_agent_prompt.kiq(agent.id)
        logger.info("Agent created", agent_id=agent.id, name=agent.name)

        return AgentResponse(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            status=agent.status,
            created_at=agent.created_at,
            document_count=0,
        )

    @router.get("/")
    async def list_agents(
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ) -> AgentListResponse:
        """List all agents for the current user"""
        agents = await agent_crud.list_user_agents(db, current_user.id)
        items = []
        for a in agents:
            doc_count = await agent_crud.get_agent_document_count(db, a.id)
            items.append(
                AgentResponse(
                    id=a.id,
                    name=a.name,
                    description=a.description,
                    system_prompt=a.system_prompt,
                    status=a.status,
                    created_at=a.created_at,
                    document_count=doc_count,
                )
            )
        return AgentListResponse(agents=items)

    @router.get("/{agent_id}")
    async def get_agent(
        agent_id: str,
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ) -> AgentResponse:
        """Get agent details"""
        agent = await agent_crud.get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent bulunamadi")
        if agent.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Yetkisiz islem")

        doc_count = await agent_crud.get_agent_document_count(db, agent_id)
        return AgentResponse(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            status=agent.status,
            created_at=agent.created_at,
            document_count=doc_count,
        )

    @router.patch("/{agent_id}")
    async def update_agent(
        agent_id: str,
        request: AgentUpdateRequest,
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ) -> AgentResponse:
        """Update agent (name, description, system_prompt)"""
        agent = await agent_crud.get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent bulunamadi")
        if agent.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Yetkisiz islem")

        updated = await agent_crud.update_agent(
            db,
            agent_id,
            name=request.name,
            description=request.description,
            system_prompt=request.system_prompt,
        )

        doc_count = await agent_crud.get_agent_document_count(db, agent_id)
        return AgentResponse(
            id=updated.id,
            name=updated.name,
            description=updated.description,
            system_prompt=updated.system_prompt,
            status=updated.status,
            created_at=updated.created_at,
            document_count=doc_count,
        )

    @router.delete("/{agent_id}")
    async def delete_agent(
        agent_id: str,
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        """Delete an agent"""
        agent = await agent_crud.get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent bulunamadi")
        if agent.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Yetkisiz islem")

        await agent_crud.delete_agent(db, agent_id)
        return {"message": "Agent silindi"}

    @router.post("/{agent_id}/documents")
    async def assign_documents(
        agent_id: str,
        request: AgentDocumentAssignRequest,
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        """Assign documents to an agent"""
        agent = await agent_crud.get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent bulunamadi")
        if agent.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Yetkisiz islem")

        await agent_crud.assign_documents(db, agent_id, request.document_ids)
        return {"message": f"{len(request.document_ids)} dokuman atandi"}

    @router.post("/by-document/{document_id}")
    async def assign_document_to_agents(
        document_id: str,
        request: DocumentAgentAssignRequest,
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        """Assign a document to multiple agents (document-centric)"""
        await agent_crud.assign_document_to_agents(db, document_id, request.agent_ids)
        return {"message": f"Dokuman {len(request.agent_ids)} agenta atandi"}

    @router.get("/by-document/{document_id}")
    async def get_document_agents(
        document_id: str,
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ) -> list[AgentResponse]:
        """Get agents that have access to a document"""
        agents = await agent_crud.get_document_agents(db, document_id)
        items = []
        for a in agents:
            if a.user_id != current_user.id:
                continue
            doc_count = await agent_crud.get_agent_document_count(db, a.id)
            items.append(
                AgentResponse(
                    id=a.id,
                    name=a.name,
                    description=a.description,
                    system_prompt=a.system_prompt,
                    status=a.status,
                    created_at=a.created_at,
                    document_count=doc_count,
                )
            )
        return items

    @router.get("/{agent_id}/documents")
    async def get_agent_documents(
        agent_id: str,
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ) -> list[AgentDocumentResponse]:
        """Get documents assigned to an agent"""
        agent = await agent_crud.get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent bulunamadi")
        if agent.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Yetkisiz islem")

        docs = await agent_crud.get_agent_documents(db, agent_id)
        return [
            AgentDocumentResponse(
                id=d.id,
                filename=d.filename,
                status=d.status,
                content_type=d.content_type,
                created_at=d.created_at,
            )
            for d in docs
        ]

    @router.get("/{agent_id}/conversations")
    async def get_agent_conversations(
        agent_id: str,
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=50),
    ) -> dict:
        """Get paginated conversations for an agent"""
        agent = await agent_crud.get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent bulunamadi")
        if agent.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Yetkisiz islem")

        skip = (page - 1) * page_size
        conversations, total = await conv_crud.list_agent_conversations(
            db, agent_id, skip=skip, limit=page_size
        )
        items = []
        for conv in conversations:
            messages = await conv_crud.list_conversation_messages(db, conv.id)
            items.append({
                "id": conv.id,
                "room_name": conv.room_name,
                "status": conv.status,
                "started_at": conv.started_at.isoformat() if conv.started_at else None,
                "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
                "summary": conv.summary,
                "message_count": len(messages),
                "messages": [
                    {
                        "id": m.id,
                        "role": "user" if m.message_type == "transcript" else "agent",
                        "content": m.content,
                        "timestamp": m.timestamp.isoformat(),
                    }
                    for m in messages
                ],
            })
        return {
            "conversations": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
        }

    @router.post("/{agent_id}/conversations/{conversation_id}/summary")
    async def generate_conversation_summary(
        agent_id: str,
        conversation_id: str,
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        """Generate or retrieve a summary for a conversation"""
        agent = await agent_crud.get_agent(db, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent bulunamadi")
        if agent.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Yetkisiz islem")

        # Check if conversation exists and belongs to this agent
        conversations, _ = await conv_crud.list_agent_conversations(db, agent_id, skip=0, limit=1000)
        conv = next((c for c in conversations if c.id == conversation_id), None)
        if not conv:
            raise HTTPException(status_code=404, detail="Konusma bulunamadi")

        # Return cached summary if exists
        if conv.summary:
            return {"summary": conv.summary}

        # Get messages
        messages = await conv_crud.list_conversation_messages(db, conversation_id)
        if not messages:
            raise HTTPException(status_code=400, detail="Bu konusmada mesaj yok")

        # Build conversation text for LLM
        conversation_text = "\n".join(
            f"{'Kullanıcı' if m.message_type == 'transcript' else 'Asistan'}: {m.content}"
            for m in messages
        )

        # Generate summary via LLM
        summary_prompt = [
            {
                "role": "system",
                "content": (
                    "Sen bir sesli sohbet özetleyicisisin. Aşağıda kullanıcı ile AI asistan arasındaki konuşma var.\n"
                    "Bu konuşmayı Türkçe olarak özetle.\n"
                    "Her madde \"•\" ile başlasın, kısa ve öz olsun. Maddeler arasında boş satır bırakma.\n"
                    "En fazla 8 madde yaz. Selamlaşma, teşekkür gibi trivial konuları atlayıp sadece bilgi içeren konuları özetle.\n"
                    "Sadece maddeleri yaz, başlık veya açıklama ekleme."
                ),
            },
            {"role": "user", "content": conversation_text},
        ]

        try:
            summary = await fal_ai_service.generate_llm_response(
                messages=summary_prompt,
                model="openai/gpt-4o-mini",
                temperature=0.3,
                max_tokens=1000,
            )
        except Exception as e:
            logger.error("Summary generation failed", error=str(e))
            raise HTTPException(status_code=500, detail="Ozet olusturulamadi")

        # Save to DB
        await conv_crud.update_conversation_summary(db, conversation_id, summary)

        return {"summary": summary}
