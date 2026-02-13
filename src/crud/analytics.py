from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from sqlalchemy import func, cast, Date
from datetime import datetime, timedelta

from src.models.sqlmodels.voice_conversation import VoiceConversation, VoiceMessage
from src.models.sqlmodels.document import Document
from src.models.sqlmodels.agent import Agent


async def get_conversation_stats(db: AsyncSession, user_id: str) -> dict:
    """Total, today, this week conversation counts."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    total_result = await db.execute(
        select(func.count())
        .select_from(VoiceConversation)
        .where(VoiceConversation.user_id == user_id)
    )
    total = total_result.scalar_one()

    today_result = await db.execute(
        select(func.count())
        .select_from(VoiceConversation)
        .where(
            VoiceConversation.user_id == user_id,
            VoiceConversation.created_at >= today_start,
        )
    )
    today = today_result.scalar_one()

    week_result = await db.execute(
        select(func.count())
        .select_from(VoiceConversation)
        .where(
            VoiceConversation.user_id == user_id,
            VoiceConversation.created_at >= week_start,
        )
    )
    this_week = week_result.scalar_one()

    return {"total": total, "today": today, "this_week": this_week}


async def get_avg_duration(db: AsyncSession, user_id: str) -> float:
    """Average conversation duration in seconds."""
    result = await db.execute(
        select(func.avg(VoiceConversation.total_duration_seconds))
        .where(
            VoiceConversation.user_id == user_id,
            VoiceConversation.total_duration_seconds > 0,
        )
    )
    return result.scalar_one() or 0


async def get_avg_message_count(db: AsyncSession, user_id: str) -> float:
    """Average number of messages per conversation."""
    # Get all conversation IDs for user
    conv_result = await db.execute(
        select(VoiceConversation.id)
        .where(VoiceConversation.user_id == user_id)
    )
    conv_ids = [r[0] for r in conv_result.all()]

    if not conv_ids:
        return 0

    msg_result = await db.execute(
        select(func.count())
        .select_from(VoiceMessage)
        .where(VoiceMessage.conversation_id.in_(conv_ids))
    )
    total_messages = msg_result.scalar_one()

    return round(total_messages / len(conv_ids), 1) if conv_ids else 0


async def get_document_stats(db: AsyncSession, user_id: str) -> dict:
    """Document counts by status."""
    result = await db.execute(
        select(Document.status, func.count())
        .where(Document.user_id == user_id)
        .group_by(Document.status)
    )
    rows = result.all()

    stats = {"total": 0, "ready": 0, "processing": 0, "pending": 0, "failed": 0}
    for status, count in rows:
        stats[status] = count
        stats["total"] += count

    return stats


async def get_top_agents(db: AsyncSession, user_id: str, limit: int = 5) -> list:
    """Top agents by conversation count."""
    result = await db.execute(
        select(
            Agent.id,
            Agent.name,
            func.count(VoiceConversation.id).label("conversation_count"),
        )
        .join(VoiceConversation, VoiceConversation.agent_id == Agent.id)
        .where(Agent.user_id == user_id)
        .group_by(Agent.id, Agent.name)
        .order_by(func.count(VoiceConversation.id).desc())
        .limit(limit)
    )
    return [
        {"id": row[0], "name": row[1], "conversation_count": row[2]}
        for row in result.all()
    ]


async def get_daily_conversations(
    db: AsyncSession, user_id: str, days: int = 7
) -> list:
    """Daily conversation counts for the last N days."""
    now = datetime.utcnow()
    start_date = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    result = await db.execute(
        select(
            cast(VoiceConversation.created_at, Date).label("date"),
            func.count().label("count"),
        )
        .where(
            VoiceConversation.user_id == user_id,
            VoiceConversation.created_at >= start_date,
        )
        .group_by(cast(VoiceConversation.created_at, Date))
        .order_by(cast(VoiceConversation.created_at, Date))
    )
    db_rows = {str(row[0]): row[1] for row in result.all()}

    # Fill in missing days with 0
    daily = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        daily.append({"date": date_str, "count": db_rows.get(date_str, 0)})

    return daily
