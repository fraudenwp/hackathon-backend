import asyncio
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar

from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError, StatementError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.constants.env import DATABASE_URL
from src.utils.logger import log_error, logger

_session_context: ContextVar = ContextVar("session_context", default=None)

minimum_unread_count: ContextVar = ContextVar("minimum_unread_count", default=None)
current_user_id = ContextVar("current_user_id")


class Database:
    _instance = None
    _engine = None
    _session_local = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._engine is None:
            try:
                self._engine = create_async_engine(
                    DATABASE_URL,
                    echo=False,
                    future=True,
                    pool_size=50,  # Reduced from 40 to prevent connection exhaustion
                    max_overflow=5,  # Reduced from 10 to limit total connections
                    pool_pre_ping=True,  # Check connection health
                    pool_recycle=1800,  # Increased to 30 minutes for long-running tasks
                    pool_timeout=20,  # Reduced from 20 seconds for faster failure
                    pool_reset_on_return="commit",  # Reset connections on return to pool
                    connect_args={
                        "server_settings": {
                            "application_name": "talenterai_backend",
                            "jit": "off",  # Disable JIT for better connection stability
                            "statement_timeout": "1800000",  # Increased to 30 minutes for long-running tasks
                            "idle_in_transaction_session_timeout": "300000",  # Increased to 5 minutes for long operation
                        }
                    },
                )

                # Attach DBAPI-level event listeners on the sync_engine to measure
                def before_cursor_execute(
                    conn, cursor, statement, parameters, context, executemany
                ):
                    try:
                        context._query_start_time = time.perf_counter()
                    except Exception:
                        pass

                def after_cursor_execute(
                    conn, cursor, statement, parameters, context, executemany
                ):
                    try:
                        start = getattr(context, "_query_start_time", None)
                        if start is None:
                            return
                        duration_ms = (time.perf_counter() - start) * 1000.0
                        threshold_ms = 600.0
                        if duration_ms > threshold_ms:
                            # Only log the statement and duration. Parameters intentionally omitted.
                            logger.warning(
                                f"Slow DB query: {duration_ms:.1f} ms | statement: {statement}",
                                component="slow_db_query",
                            )
                    except Exception as e:
                        # Never let logging interfere with DB execution
                        log_error(
                            logger,
                            "Failed to log slow query",
                            e,
                            component="slow_db_query",
                        )

                try:
                    # Use sync_engine to attach DBAPI cursor-level events (works for async engine)
                    event.listen(
                        self._engine.sync_engine,
                        "before_cursor_execute",
                        before_cursor_execute,
                    )
                    event.listen(
                        self._engine.sync_engine,
                        "after_cursor_execute",
                        after_cursor_execute,
                    )
                except Exception as e:
                    # Non-fatal: if event attachment fails, continue but log the failure
                    log_error(
                        logger,
                        "Attaching slow-query event listeners failed",
                        e,
                        component="sqlalchemy_events",
                    )
            except Exception as e:
                log_error(
                    logger,
                    "Database engine creation failed",
                    e,
                    component="sqlalchemy_engine",
                )
                raise

            try:
                self._session_local = async_sessionmaker(
                    self._engine,
                    expire_on_commit=False,
                    autoflush=False,  # Prevent automatic flushing
                    autocommit=False,
                )
            except Exception as e:
                log_error(
                    logger,
                    "Database session factory creation failed",
                    e,
                    component="sqlalchemy_sessionmaker",
                )
                raise

    @property
    def engine(self):
        return self._engine

    @property
    def session_local(self):
        return self._session_local

    @asynccontextmanager
    async def get_session_context(self):
        # Mevcut session var mı kontrol et
        existing_session = _session_context.get()
        if existing_session:
            # Mevcut session'ı kullan, commit/rollback yapma
            yield existing_session
            return

        # Yeni session oluştur
        try:
            session = self.session_local()
        except Exception as e:
            log_error(
                logger,
                "Session creation failed",
                e,
                component="sqlalchemy_session_create",
            )
            raise
        _session_context.set(session)
        try:
            yield session
        except Exception as e:
            try:
                await session.rollback()
            except Exception as rb_e:
                log_error(
                    logger,
                    "Session rollback failed",
                    rb_e,
                    component="sqlalchemy_session_rollback",
                )
            raise e
        finally:
            _session_context.set(None)
            try:
                await session.close()
            except Exception as cl_e:
                log_error(
                    logger,
                    "Session close failed",
                    cl_e,
                    component="sqlalchemy_session_close",
                )

    async def close_all_connections(self):
        """Close all database connections - useful for cleanup"""
        if self._engine:
            await self._engine.dispose()

    @asynccontextmanager
    async def get_long_running_session_context(self, heartbeat_interval: int = 60):
        """
        Session context manager specifically designed for long-running tasks.

        Features:
        - Automatic connection health monitoring
        - Periodic heartbeat to prevent timeouts
        - Auto-recovery from connection losses
        - Proper error handling and retry logic

        Args:
            heartbeat_interval: Seconds between heartbeat checks (default 60s)
        """
        session = self.session_local()
        heartbeat_task = None

        try:
            # Start heartbeat task for connection health monitoring
            heartbeat_task = asyncio.create_task(
                self._heartbeat_task(session, heartbeat_interval)
            )

            yield session

        except Exception as e:
            logger.error(f"Error in long-running session: {e}")
            await session.rollback()
            raise e
        finally:
            # Cancel heartbeat task
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

            await session.close()

    async def _heartbeat_task(self, session: AsyncSession, interval: int):
        """
        Background task that sends periodic heartbeats to keep the connection alive
        and detect connection issues early.
        """
        retry_count = 0
        max_retries = 3

        while True:
            try:
                await asyncio.sleep(interval)

                # Send a simple heartbeat query
                await session.execute(text("SELECT 1"))
                logger.debug("Database heartbeat successful")
                retry_count = 0  # Reset retry count on success

            except asyncio.CancelledError:
                # Task was cancelled, exit gracefully
                break
            except (OperationalError, StatementError) as e:
                retry_count += 1
                logger.warning(
                    f"Database heartbeat failed (attempt {retry_count}/{max_retries}): {e}"
                )

                if retry_count >= max_retries:
                    logger.error(
                        "Max heartbeat retries exceeded, connection may be lost"
                    )
                    break

                # Wait a bit before retrying
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error in heartbeat task: {e}")
                break

    async def refresh_session_connection(self, session: AsyncSession) -> bool:
        """
        Attempt to refresh a database session connection.

        Returns:
            bool: True if refresh was successful, False otherwise
        """
        try:
            # First try to rollback any pending transaction
            await session.rollback()

            # Test the connection with a simple query
            await session.execute(text("SELECT 1"))
            logger.info("Database session connection refreshed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to refresh database session connection: {e}")
            return False


# Create a global instance
db = Database()
