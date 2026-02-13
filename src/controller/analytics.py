from typing import Annotated

from fastapi import APIRouter, Depends, Security
from sqlmodel.ext.asyncio.session import AsyncSession

from src.crud.auth import AuthCRUD
from src.crud import analytics as analytics_crud
from src.models.dependency import get_session
from src.models.sqlmodels.user import User


class AnalyticsController:
    tags = ["analytics"]
    router = APIRouter(tags=tags)

    @router.get("/overview")
    async def get_overview(
        current_user: Annotated[
            User, Security(AuthCRUD.get_current_user_with_access())
        ],
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        """Get analytics overview for the current user."""
        conv_stats = await analytics_crud.get_conversation_stats(db, current_user.id)
        avg_duration = await analytics_crud.get_avg_duration(db, current_user.id)
        avg_messages = await analytics_crud.get_avg_message_count(db, current_user.id)
        doc_stats = await analytics_crud.get_document_stats(db, current_user.id)
        top_agents = await analytics_crud.get_top_agents(db, current_user.id)
        daily = await analytics_crud.get_daily_conversations(db, current_user.id)

        return {
            "total_conversations": conv_stats["total"],
            "conversations_today": conv_stats["today"],
            "conversations_this_week": conv_stats["this_week"],
            "avg_duration_seconds": round(float(avg_duration), 1),
            "avg_message_count": float(avg_messages),
            "total_documents": doc_stats["total"],
            "documents_ready": doc_stats["ready"],
            "documents_processing": doc_stats.get("processing", 0) + doc_stats.get("pending", 0),
            "documents_failed": doc_stats["failed"],
            "top_agents": top_agents,
            "daily_conversations": daily,
        }
