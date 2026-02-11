from sqlmodel import Field, SQLModel
from datetime import datetime
from typing import Optional
import uuid


class VoiceConversation(SQLModel, table=True):
    __tablename__ = "voice_conversations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    room_name: str = Field(index=True, unique=True)
    room_sid: Optional[str] = None

    status: str = Field(default="active")  # active, ended, error
    ai_enabled: bool = Field(default=False)

    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None

    total_duration_seconds: int = Field(default=0)
    participant_count: int = Field(default=0)

    config: dict = Field(default={}, sa_column_kwargs={"type_": "jsonb"})

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class VoiceMessage(SQLModel, table=True):
    __tablename__ = "voice_messages"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(
        foreign_key="voice_conversations.id", index=True
    )

    participant_identity: str = Field(index=True)
    participant_name: str

    message_type: str  # transcript, ai_response, system
    content: str

    timestamp: datetime = Field(default_factory=datetime.utcnow)
