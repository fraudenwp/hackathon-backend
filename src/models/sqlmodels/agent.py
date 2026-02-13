from sqlmodel import Field, SQLModel
from datetime import datetime
from typing import Optional
import uuid


class Agent(SQLModel, table=True):
    __tablename__ = "agent"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True
    )
    user_id: str = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    name: str = Field(...)
    description: str = Field(default="")
    system_prompt: str = Field(default="")
    status: str = Field(default="generating")  # generating, ready, failed

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs=dict(onupdate=datetime.now),
    )


class AgentDocument(SQLModel, table=True):
    __tablename__ = "agent_document"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True
    )
    agent_id: str = Field(foreign_key="agent.id", ondelete="CASCADE", index=True)
    document_id: str = Field(foreign_key="document.id", ondelete="CASCADE", index=True)

    created_at: datetime = Field(default_factory=datetime.now)
