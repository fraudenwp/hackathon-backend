from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from sqlmodel.ext.asyncio.session import AsyncSession

from src.crud.auth import AuthCRUD
from src.crud import voice_conversation as conv_crud
from src.crud import agent as agent_crud
from src.models.dependency import get_session
from src.models.sqlmodels.user import User


class ConversationController:
    tags = ["conversation"]
    router = APIRouter(tags=tags)

    @router.get("/")
    async def list_user_conversations(
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ) -> dict:
        """Get paginated conversations for the current user"""
        skip = (page - 1) * page_size
        conversations, total = await conv_crud.list_user_conversations(
            db, current_user.id, skip=skip, limit=page_size
        )

        items = []
        for conv in conversations:
            messages = await conv_crud.list_conversation_messages(db, conv.id)

            # Get agent name if exists
            agent_name = None
            if conv.agent_id:
                agent = await agent_crud.get_agent(db, conv.agent_id)
                if agent:
                    agent_name = agent.name

            items.append({
                "id": conv.id,
                "agent_id": conv.agent_id,
                "agent_name": agent_name,
                "room_name": conv.room_name,
                "status": conv.status,
                "started_at": conv.started_at.isoformat() if conv.started_at else None,
                "ended_at": conv.ended_at.isoformat() if conv.ended_at else None,
                "total_duration_seconds": conv.total_duration_seconds,
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
