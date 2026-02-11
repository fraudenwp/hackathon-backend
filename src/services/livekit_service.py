"""
LiveKit Service - Room and token management
"""

from typing import Any, Dict, List, Optional

from livekit import api

from src.constants.env import LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
from src.utils.logger import get_logger, log_error

logger = get_logger(__name__)


class LiveKitService:
    """Service for LiveKit room and token management"""

    def __init__(
        self,
        url: str = LIVEKIT_URL,
        api_key: str = LIVEKIT_API_KEY,
        api_secret: str = LIVEKIT_API_SECRET,
    ):
        self.url = url
        self.api_key = api_key
        self.api_secret = api_secret
        self._lk_api = None

    @staticmethod
    def _create_livekit_api(url: str, api_key: str, api_secret: str) -> api.LiveKitAPI:
        if not all([url, api_key, api_secret]):
            raise ValueError("LiveKit configuration is incomplete")
        return api.LiveKitAPI(url=url, api_key=api_key, api_secret=api_secret)

    @property
    def lk_api(self):
        """Lazy initialize LiveKit API client"""
        if self._lk_api is None:
            self._lk_api = self._create_livekit_api(
                self.url, self.api_key, self.api_secret
            )
        return self._lk_api

    async def generate_token(
        self,
        room_name: str,
        participant_identity: str,
        participant_name: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Generate access token for room"""
        try:
            token = api.AccessToken(self.api_key, self.api_secret)
            token.with_identity(participant_identity)
            token.with_name(participant_name)
            token.with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                )
            )
            if metadata:
                token.with_metadata(str(metadata))

            return token.to_jwt()

        except Exception as e:
            log_error(logger, "Token generation failed", e, room=room_name)
            raise

    async def create_room(
        self,
        name: str,
        empty_timeout: int = 300,
        max_participants: int = 50,
    ) -> Any:
        """Create a new room"""
        try:
            room = await self.lk_api.room.create_room(
                api.CreateRoomRequest(
                    name=name,
                    empty_timeout=empty_timeout,
                    max_participants=max_participants,
                )
            )
            return room

        except Exception as e:
            log_error(logger, "Room creation failed", e, room=name)
            raise

    async def get_room(self, name: str) -> Any:
        """Get room details"""
        try:
            rooms = await self.lk_api.room.list_rooms(
                api.ListRoomsRequest(names=[name])
            )
            return rooms[0] if rooms else None

        except Exception as e:
            log_error(logger, "Get room failed", e, room=name)
            raise

    async def list_rooms(self) -> List[Any]:
        """List all active rooms"""
        try:
            rooms = await self.lk_api.room.list_rooms(api.ListRoomsRequest())
            return rooms

        except Exception as e:
            log_error(logger, "List rooms failed", e)
            raise

    async def delete_room(self, name: str) -> None:
        """Delete a room"""
        try:
            await self.lk_api.room.delete_room(api.DeleteRoomRequest(room=name))

        except Exception as e:
            log_error(logger, "Delete room failed", e, room=name)
            raise

    async def list_participants(self, room_name: str) -> List[Any]:
        """List participants in a room"""
        try:
            participants = await self.lk_api.room.list_participants(
                api.ListParticipantsRequest(room=room_name)
            )
            return participants

        except Exception as e:
            log_error(logger, "List participants failed", e, room=room_name)
            raise


# Singleton instance
livekit_service = LiveKitService()
