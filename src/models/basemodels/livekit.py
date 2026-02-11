from pydantic import BaseModel, Field
from typing import Optional, List


class RoomCreateRequest(BaseModel):
    name: Optional[str] = None  # Auto-generate if not provided
    max_participants: int = Field(default=50, ge=2, le=100)
    empty_timeout: int = Field(default=300, ge=60, le=3600)


class TokenResponse(BaseModel):
    token: str
    room_name: str
    ws_url: str
    participant_identity: str


class RoomResponse(BaseModel):
    room_name: str
    sid: str
    num_participants: int
    max_participants: int
    created_at: int


class RoomListResponse(BaseModel):
    rooms: List[RoomResponse]


class MakeCallRequest(BaseModel):
    system_prompt: Optional[str] = None  # Custom AI instructions
    max_participants: int = Field(default=50, ge=2, le=100)
    empty_timeout: int = Field(default=300, ge=60, le=3600)


class MakeCallResponse(BaseModel):
    token: str
    room_name: str
    ws_url: str
    participant_identity: str
    room_sid: str
    ai_enabled: bool
    message: str
