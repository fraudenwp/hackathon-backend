from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security
from sqlmodel.ext.asyncio.session import AsyncSession
import uuid

from src.crud.auth import AuthCRUD
from src.models.dependency import get_session
from src.models.sqlmodels.user import User
from src.models.basemodels.livekit import (
    RoomCreateRequest,
    TokenResponse,
    RoomResponse,
    RoomListResponse,
    MakeCallRequest,
    MakeCallResponse,
)
from src.services.livekit_service import livekit_service
from src.services.voice_agent import get_agent
from src.crud import voice_conversation
from src.constants.env import LIVEKIT_WS_URL
from src.tasks.voice.voice_agent_task import start_voice_agent_task, stop_voice_agent_task


class LiveKitController:
    tags = ["livekit"]
    router = APIRouter(tags=tags)

    @router.post("/make-call")
    async def make_call(
        request: MakeCallRequest,
        current_user: Annotated[
            User,
            Security(
                AuthCRUD.get_current_user_with_access(),
            ),
        ],
        db: AsyncSession = Depends(get_session),
    ) -> MakeCallResponse:
        """Create room, start AI agent, and return connection token - all in one call"""
        # Generate unique room name
        room_name = f"room-{uuid.uuid4()}"

        # Create room in LiveKit
        room = await livekit_service.create_room(
            name=room_name,
            empty_timeout=request.empty_timeout,
            max_participants=request.max_participants,
        )

        # Save to database
        conversation = await voice_conversation.create_conversation(
            db=db,
            user_id=current_user.id,
            room_name=room.name,
            room_sid=room.sid,
        )

        # Mark AI as enabled (will start in background)
        conversation.ai_enabled = True
        await db.commit()

        # Generate access token for user
        token = await livekit_service.generate_token(
            room_name=room_name,
            participant_identity=str(current_user.id),
            participant_name=current_user.email,
            metadata={"user_id": str(current_user.id)},
        )

        # Start AI agent in background using Taskiq
        await start_voice_agent_task.kiq(room_name, system_prompt=request.system_prompt)

        return MakeCallResponse(
            token=token,
            room_name=room_name,
            ws_url=LIVEKIT_WS_URL,
            participant_identity=str(current_user.id),
            room_sid=room.sid,
            ai_enabled=True,
            message="Voice call ready! AI agent is starting in background. Connect using the provided token and ws_url.",
        )

    @router.post("/rooms/create")
    async def create_room(
        room_request: RoomCreateRequest,
        current_user: Annotated[
            User,
            Security(
                AuthCRUD.get_current_user_with_access(),
            ),
        ],
        db: AsyncSession = Depends(get_session),
    ) -> RoomResponse:
        """Create a new LiveKit room"""
        # Generate room name if not provided
        room_name = room_request.name or f"room-{uuid.uuid4()}"

        # Create room in LiveKit
        room = await livekit_service.create_room(
            name=room_name,
            empty_timeout=room_request.empty_timeout,
            max_participants=room_request.max_participants,
        )

        # Save to database
        await voice_conversation.create_conversation(
            db=db,
            user_id=current_user.id,
            room_name=room.name,
            room_sid=room.sid,
        )

        return RoomResponse(
            room_name=room.name,
            sid=room.sid,
            num_participants=room.num_participants,
            max_participants=room.max_participants,
            created_at=room.creation_time,
        )

    @router.get("/rooms/{room_name}/token")
    async def get_room_token(
        room_name: str,
        current_user: Annotated[
            User,
            Security(
                AuthCRUD.get_current_user_with_access(),
            ),
        ],
    ) -> TokenResponse:
        """Generate access token for joining a room"""
        # Generate access token
        token = await livekit_service.generate_token(
            room_name=room_name,
            participant_identity=str(current_user.id),
            participant_name=current_user.email,
            metadata={"user_id": str(current_user.id)},
        )

        return TokenResponse(
            token=token,
            room_name=room_name,
            ws_url=LIVEKIT_WS_URL,
            participant_identity=str(current_user.id),
        )

    @router.get("/rooms")
    async def list_rooms(
        current_user: Annotated[
            User,
            Security(
                AuthCRUD.get_current_user_with_access(),
            ),
        ],
        db: AsyncSession = Depends(get_session),
    ) -> RoomListResponse:
        """List all rooms for the current user"""
        # Get user's conversations from DB
        conversations = await voice_conversation.list_user_conversations(
            db=db, user_id=current_user.id
        )

        # Get current room status from LiveKit
        all_rooms = await livekit_service.list_rooms()
        room_map = {r.name: r for r in all_rooms}

        rooms = []
        for conv in conversations:
            if conv.room_name in room_map:
                r = room_map[conv.room_name]
                rooms.append(
                    RoomResponse(
                        room_name=r.name,
                        sid=r.sid,
                        num_participants=r.num_participants,
                        max_participants=r.max_participants,
                        created_at=r.creation_time,
                    )
                )

        return RoomListResponse(rooms=rooms)

    @router.delete("/rooms/{room_name}")
    async def delete_room(
        room_name: str,
        current_user: Annotated[
            User,
            Security(
                AuthCRUD.get_current_user_with_access(),
            ),
        ],
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        """Delete a room"""
        # Get conversation from DB
        conversation = await voice_conversation.get_conversation_by_room(
            db=db, room_name=room_name
        )

        if not conversation:
            raise HTTPException(status_code=404, detail="Room not found")

        if conversation.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Delete from LiveKit
        await livekit_service.delete_room(room_name)

        # Update DB
        await voice_conversation.end_conversation(db=db, conversation_id=conversation.id)

        return {"message": "Room deleted successfully"}

    @router.post("/rooms/{room_name}/start-ai")
    async def start_ai_agent(
        room_name: str,
        current_user: Annotated[
            User,
            Security(
                AuthCRUD.get_current_user_with_access(),
            ),
        ],
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        """Start AI agent in a room"""
        # Verify user owns the room
        conversation = await voice_conversation.get_conversation_by_room(
            db=db, room_name=room_name
        )

        if not conversation:
            raise HTTPException(status_code=404, detail="Room not found")

        if conversation.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Check if agent already running
        if get_agent(room_name):
            raise HTTPException(status_code=400, detail="Agent already running")

        # Update DB
        conversation.ai_enabled = True
        await db.commit()

        # Start agent using Taskiq
        await start_voice_agent_task.kiq(room_name)

        return {"message": "AI agent is starting in background", "room_name": room_name}

    @router.post("/rooms/{room_name}/stop-ai")
    async def stop_ai_agent(
        room_name: str,
        current_user: Annotated[
            User,
            Security(
                AuthCRUD.get_current_user_with_access(),
            ),
        ],
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        """Stop AI agent in a room"""
        # Verify user owns the room
        conversation = await voice_conversation.get_conversation_by_room(
            db=db, room_name=room_name
        )

        if not conversation:
            raise HTTPException(status_code=404, detail="Room not found")

        if conversation.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")

        # Check if agent is running
        if not get_agent(room_name):
            raise HTTPException(status_code=400, detail="No agent running in this room")

        # Update DB
        conversation.ai_enabled = False
        await db.commit()

        # Stop agent using Taskiq
        await stop_voice_agent_task.kiq(room_name)

        return {"message": "AI agent is stopping in background", "room_name": room_name}
