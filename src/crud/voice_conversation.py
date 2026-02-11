from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from typing import List, Optional
from datetime import datetime
import uuid

from src.models.sqlmodels.voice_conversation import VoiceConversation


async def create_conversation(
    db: AsyncSession, user_id: uuid.UUID, room_name: str, room_sid: str
) -> VoiceConversation:
    conversation = VoiceConversation(
        user_id=user_id, room_name=room_name, room_sid=room_sid
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
    db: AsyncSession, user_id: uuid.UUID
) -> List[VoiceConversation]:
    result = await db.execute(
        select(VoiceConversation).where(VoiceConversation.user_id == user_id)
    )
    return result.scalars().all()


async def end_conversation(
    db: AsyncSession, conversation_id: uuid.UUID
) -> VoiceConversation:
    result = await db.execute(
        select(VoiceConversation).where(VoiceConversation.id == conversation_id)
    )
    conversation = result.scalar_one()
    conversation.status = "ended"
    conversation.ended_at = datetime.utcnow()
    await db.commit()
    await db.refresh(conversation)
    return conversation
