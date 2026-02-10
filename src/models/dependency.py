import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import db

logger = logging.getLogger(__name__)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI session dependency with automatic transaction management.

    Key principles:
    - Session auto-commits on successful completion
    - Session auto-rollbacks on exceptions
    - No manual commit/rollback needed in endpoints
    - Connection timeouts prevent idle connections
    """
    async with db.get_session_context() as session:
        yield session


async def get_long_running_session(
    heartbeat_interval: int = 60,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Session dependency specifically designed for long-running tasks.

    Features:
    - Extended timeouts for long operations
    - Automatic connection health monitoring
    - Periodic heartbeat to prevent timeouts
    - Auto-recovery from connection losses

    Args:
        heartbeat_interval: Seconds between heartbeat checks (default 60s)

    Usage:
        @broker.task
        async def long_task(db: AsyncSession = TaskiqDepends(get_long_running_session)):
            # Your long-running task logic here
            pass
    """
    async with db.get_long_running_session_context(heartbeat_interval) as session:
        yield session
