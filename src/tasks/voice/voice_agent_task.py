"""Voice agent background tasks"""

from typing import Optional

from src.tasks.taskiq_setup import broker
from src.services.voice_agent import (
    start_agent as _start_agent,
    stop_agent as _stop_agent,
)
from src.utils.logger import logger


@broker.task
async def start_voice_agent_task(
    room_name: str,
    system_prompt: Optional[str] = None,
    user_id: Optional[str] = None,
    doc_ids: Optional[list[str]] = None,
):
    """Start voice agent in background and keep it alive until disconnect"""
    logger.info(f"Starting voice agent for room: {room_name}")
    try:
        agent = await _start_agent(room_name, system_prompt=system_prompt, user_id=user_id, doc_ids=doc_ids)
        logger.info(f"Voice agent started successfully for room: {room_name}")

        # Block until room disconnects or agent is stopped
        await agent.wait_until_done()

        logger.info(f"Voice agent session ended for room: {room_name}")
        return {"success": True, "room_name": room_name}
    except Exception as e:
        logger.error(f"Failed to start voice agent for room {room_name}: {e}")
        raise


@broker.task
async def stop_voice_agent_task(room_name: str):
    """Stop voice agent in background"""
    logger.info(f"Stopping voice agent for room: {room_name}")
    try:
        await _stop_agent(room_name)
        logger.info(f"Voice agent stopped successfully for room: {room_name}")
        return {"success": True, "room_name": room_name}
    except Exception as e:
        logger.error(f"Failed to stop voice agent for room {room_name}: {e}")
        raise
