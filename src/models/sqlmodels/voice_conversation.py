from sqlmodel import Column, Field, SQLModel
from sqlalchemy.dialects.postgresql import JSON
from datetime import datetime
from typing import Dict, Optional
import uuid


class VoiceConversation(SQLModel, table=True):
    __tablename__ = "voice_conversation"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True
    )
    user_id: str = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    agent_id: Optional[str] = Field(default=None, foreign_key="agent.id", ondelete="SET NULL", index=True)
    room_name: str = Field(index=True, unique=True)
    room_sid: Optional[str] = None

    status: str = Field(default="active")  # active, ended, error
    ai_enabled: bool = Field(default=False)

    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None

    total_duration_seconds: int = Field(default=0)
    participant_count: int = Field(default=0)

    summary: Optional[str] = Field(default=None)

    config: Dict = Field(default={}, sa_column=Column(JSON, nullable=False))

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs=dict(onupdate=datetime.now),
    )


class VoiceMessage(SQLModel, table=True):
    __tablename__ = "voice_message"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    conversation_id: str = Field(foreign_key="voice_conversation.id", ondelete="CASCADE", index=True)

    participant_identity: str = Field(index=True)
    participant_name: str = Field(...)

    message_type: str = Field(..., description="transcript, ai_response, system")
    content: str = Field(...)

    timestamp: datetime = Field(default_factory=datetime.utcnow)
