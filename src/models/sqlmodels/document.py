from sqlmodel import Field, SQLModel
from datetime import datetime
from typing import Optional
import uuid


class Document(SQLModel, table=True):
    __tablename__ = "document"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), primary_key=True, index=True
    )
    user_id: str = Field(foreign_key="user.id", index=True)
    filename: str = Field(...)
    r2_key: str = Field(...)
    content_type: str = Field(default="application/octet-stream")

    status: str = Field(default="pending")  # pending, processing, ready, failed
    chunk_count: int = Field(default=0)
    error_message: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs=dict(onupdate=datetime.now),
    )
