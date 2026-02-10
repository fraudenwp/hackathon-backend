from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import CITEXT
from sqlmodel import Field, SQLModel


class UserBase(SQLModel):
    username: str = Field(
        min_length=3,
        max_length=40,
        sa_column=Column(CITEXT, unique=True, nullable=False),
    )


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=40)


class User(UserBase, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    disabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs=dict(onupdate=datetime.now),
    )
    hashed_password: str = Field(..., exclude=True)
