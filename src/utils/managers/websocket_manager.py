import asyncio
from typing import Dict, List

import orjson
import redis.asyncio as aioredis
from fastapi import WebSocket

from src.constants.env import VALKEY_WEBSOCKET_URL
from src.utils.logger import log_error, logger


# --------------------------------------
# ChannelType: Channel Constants
# --------------------------------------
class ChannelType:
    AUTOMATION = "automation"


# --------------------------------------
# RedisPubSubManager: Manages Redis Pub/Sub Connections
# --------------------------------------
class RedisPubSubManager:
    """
    Manages Redis Pub/Sub connections.
    """

    def __init__(self):
        self.redis_connection = None

    async def _get_redis_connection(self):
        if not self.redis_connection:
            try:
                self.redis_connection = aioredis.from_url(
                    VALKEY_WEBSOCKET_URL,
                    # Keep the connection healthy for long-lived pubsub streams
                    health_check_interval=30,
                    socket_keepalive=True,
                    retry_on_timeout=True,
                    socket_connect_timeout=5,
                    socket_timeout=10,
                    auto_close_connection_pool=False,
                    decode_responses=True,
                )

            except Exception as e:
                log_error(
                    logger,
                    "Redis connection failed",
                    e,
                    component="websocket_pubsub",
                )
                self.redis_connection = None
                raise
        return self.redis_connection

    async def connect(self):
        # Sadece redis bağlantısının varlığını garanti altına alır.
        await self._get_redis_connection()

    async def _publish(self, channel: str, message: str):
        try:
            redis_conn = await self._get_redis_connection()
            await redis_conn.publish(channel, message)
        except Exception as e:
            log_error(
                logger,
                "Redis publish failed",
                e,
                component="websocket_pubsub",
            )
            raise

    async def subscribe(self, channel: str):
        """
        Her çağrıda yeni bir pubsub örneği oluşturur ve ilgili kanala abone olur.
        """
        try:
            redis_conn = await self._get_redis_connection()
            pubsub = redis_conn.pubsub()
            await pubsub.subscribe(channel)
            return pubsub
        except Exception as e:
            log_error(
                logger,
                "Redis subscribe failed",
                e,
                component="websocket_pubsub",
            )
            raise

    async def unsubscribe(self, pubsub, channel: str):
        try:
            if pubsub.connection is not None and pubsub.connection.is_connected:
                await pubsub.unsubscribe(channel)
            await pubsub.close()
        except AttributeError:
            # bağlantı kopmuş -> writer None
            await pubsub.close()
        except Exception as e:
            log_error(
                logger,
                "Redis unsubscribe failed",
                e,
                component="websocket_pubsub",
            )


# --------------------------------------
# ClientConnection: Represents a WebSocket Connection (JSON Messaging)
# --------------------------------------
class ClientConnection:
    def __init__(
        self,
        websocket: WebSocket,
        user_id: str,
        conversation_id: str,
        channel_type: str,
    ):
        self.websocket = websocket
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.channel_type = channel_type

    async def send(self, message: dict):
        await self.websocket.send_json(message)

    async def close(self):
        await self.websocket.close()


# --------------------------------------
# ChannelManager: Manages Conversation Channels
# --------------------------------------
class ChannelManager:
    def __init__(self, redis_manager: RedisPubSubManager):
        self.redis_manager = redis_manager
        # conversation_id -> List[ClientConnection]
        self.local_channel_members: Dict[str, List[ClientConnection]] = {}
        # conversation_id -> listener task
        self.listener_tasks: Dict[str, asyncio.Task] = {}
        # conversation_id -> pubsub instance
        self.pubsub_subscribers: Dict[str, any] = {}

    async def join_conversation(self, conn: ClientConnection):
        cid = conn.conversation_id
        if cid not in self.local_channel_members:
            self.local_channel_members[cid] = []
            await self.redis_manager.connect()
            channel = f"{conn.channel_type}:{cid}"
            pubsub_subscriber = await self.redis_manager.subscribe(channel)
            self.pubsub_subscribers[cid] = pubsub_subscriber
            task = asyncio.create_task(
                self._pubsub_data_reader(pubsub_subscriber, cid, channel)
            )
            self.listener_tasks[cid] = task
        self.local_channel_members[cid].append(conn)

    async def leave_conversation(self, conn: ClientConnection):
        cid = conn.conversation_id
        if cid in self.local_channel_members:
            self.local_channel_members[cid] = [
                c for c in self.local_channel_members[cid] if c != conn
            ]
            if not self.local_channel_members[cid]:
                channel = f"{conn.channel_type}:{cid}"
                pubsub_subscriber = self.pubsub_subscribers.get(cid)
                if pubsub_subscriber:
                    await self.redis_manager.unsubscribe(pubsub_subscriber, channel)
                    del self.pubsub_subscribers[cid]
                if cid in self.listener_tasks:
                    self.listener_tasks[cid].cancel()
                    del self.listener_tasks[cid]
                del self.local_channel_members[cid]

    async def broadcast_local(self, conversation_id: str, message):
        if conversation_id not in self.local_channel_members:
            return

        if isinstance(message, dict) and message.get("type") == "message":
            try:
                data_payload = orjson.loads(message["data"])
            except Exception:
                data_payload = message["data"]
        else:
            try:
                data_payload = orjson.loads(message)
            except Exception:
                data_payload = message

        for conn in self.local_channel_members[conversation_id]:
            await conn.send(data_payload)

    async def _pubsub_data_reader(
        self, pubsub_subscriber, conversation_id: str, expected_channel: str
    ):
        try:
            async for message in pubsub_subscriber.listen():
                # Sadece beklenen kanala ait, "message" tipindeki mesajları ilet.
                if (
                    message.get("type") == "message"
                    and message.get("channel") == expected_channel
                ):
                    await self.broadcast_local(conversation_id, message)
        except Exception:
            # log_error(
            #     logger,
            #     "Redis pubsub data reader failed",
            #     e,
            #     component="websocket_pubsub",
            # )
            pass


# --------------------------------------
# WebSocketManager: Main Router
# --------------------------------------
class WebSocketManager:
    _instance = None
    connections: Dict[str, List[ClientConnection]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WebSocketManager, cls).__new__(cls)
            cls._instance.redis_manager = RedisPubSubManager()
            cls._instance.channel_manager = ChannelManager(cls._instance.redis_manager)
            cls._instance.connections = {}
        return cls._instance

    def __init__(self):
        # Initialization is handled in __new__
        pass

    async def on_client_connected(
        self,
        websocket: WebSocket,
        user_id: str,
        conversation_id: str,
        channel_type: str,
    ):
        await websocket.accept()
        conn = ClientConnection(websocket, user_id, conversation_id, channel_type)
        if user_id not in self.connections:
            self.connections[user_id] = []
        self.connections[user_id].append(conn)
        await self.channel_manager.join_conversation(conn)
        return conn

    async def publish_message(
        self,
        channel_type: str,
        conversation_id: str,
        message: dict,
        suppress_error: bool = False,
    ):
        """
        Publish function that can be called externally.
        Converts the message dict to a JSON string and sends it to the corresponding Redis channel.
        """
        try:
            channel = f"{channel_type}:{conversation_id}"
            message_str = orjson.dumps(message).decode("utf-8")
            await self.redis_manager._publish(channel, message_str)
        except Exception as e:
            if suppress_error:
                log_error(
                    logger,
                    "WebSocketManager.publish_message failed.",
                    e,
                    channel_type=channel_type,
                    conversation_id=conversation_id,
                    message=str(message)[:100],
                    suppress_error=suppress_error,
                )
            else:
                raise e

    async def _on_client_disconnected(self, conn: ClientConnection):
        user_id = conn.user_id
        if user_id in self.connections:
            self.connections[user_id] = [
                c for c in self.connections[user_id] if c != conn
            ]
            if not self.connections[user_id]:
                del self.connections[user_id]
        await self.channel_manager.leave_conversation(conn)
        try:
            await conn.close()
        except Exception:
            pass

    async def close(self):
        """
        Close all WebSocket connections and clean up resources.
        This should be called when shutting down the application.
        """
        for user_id, connections in list(self.connections.items()):
            for conn in connections:
                try:
                    await self._on_client_disconnected(conn)
                except Exception as e:
                    print(f"Error closing connection for user {user_id}: {str(e)}")
        self.connections.clear()
        if self.redis_manager.redis_connection:
            await self.redis_manager.redis_connection.close()
