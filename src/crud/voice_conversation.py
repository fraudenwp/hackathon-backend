from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime
import uuid

from src.models.sqlmodels.voice_conversation import VoiceConversation, VoiceMessage


async def create_conversation(
    db: AsyncSession, user_id: uuid.UUID, room_name: str, room_sid: str,
    agent_id: Optional[str] = None,
) -> VoiceConversation:
    conversation = VoiceConversation(
        user_id=user_id, room_name=room_name, room_sid=room_sid, agent_id=agent_id,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def get_conversation_by_room(
    db: AsyncSession, room_name: str
) -> Optional[VoiceConversation]:
    result = await db.execute(
        select(VoiceConversation).where(VoiceConversation.room_name == room_name)
    )
    return result.scalar_one_or_none()


async def list_user_conversations(
    db: AsyncSession, user_id: uuid.UUID, skip: int = 0, limit: int = 20
) -> tuple[List[VoiceConversation], int]:
    count_result = await db.execute(
        select(func.count())
        .select_from(VoiceConversation)
        .where(VoiceConversation.user_id == user_id)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(VoiceConversation)
        .where(VoiceConversation.user_id == user_id)
        .order_by(VoiceConversation.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all(), total


async def list_agent_conversations(
    db: AsyncSession, agent_id: str,
    skip: int = 0, limit: int = 10,
) -> tuple[List[VoiceConversation], int]:
    count_result = await db.execute(
        select(func.count())
        .select_from(VoiceConversation)
        .where(VoiceConversation.agent_id == agent_id)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(VoiceConversation)
        .where(VoiceConversation.agent_id == agent_id)
        .order_by(VoiceConversation.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all(), total


async def create_message(
    db: AsyncSession,
    conversation_id: str,
    participant_identity: str,
    participant_name: str,
    message_type: str,
    content: str,
) -> VoiceMessage:
    msg = VoiceMessage(
        conversation_id=conversation_id,
        participant_identity=participant_identity,
        participant_name=participant_name,
        message_type=message_type,
        content=content,
    )
    db.add(msg)
    await db.commit()
    return msg


async def list_conversation_messages(
    db: AsyncSession, conversation_id: str
) -> List[VoiceMessage]:
    result = await db.execute(
        select(VoiceMessage)
        .where(VoiceMessage.conversation_id == conversation_id)
        .order_by(VoiceMessage.timestamp.asc())
    )
    return result.scalars().all()


async def update_conversation_summary(
    db: AsyncSession, conversation_id: str, summary: str,
) -> Optional[VoiceConversation]:
    result = await db.execute(
        select(VoiceConversation).where(VoiceConversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        return None
    conversation.summary = summary
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def end_conversation(
    db: AsyncSession, conversation_id: uuid.UUID, participant_count: int = 0,
) -> Optional[VoiceConversation]:
    result = await db.execute(
        select(VoiceConversation).where(VoiceConversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if not conversation or conversation.status == "ended":
        return conversation
    conversation.status = "ended"
    conversation.ended_at = datetime.utcnow()
    if conversation.started_at:
        duration = (conversation.ended_at - conversation.started_at).total_seconds()
        conversation.total_duration_seconds = int(duration)
    if participant_count > 0:
        conversation.participant_count = participant_count
    await db.commit()
    await db.refresh(conversation)
    return conversation
