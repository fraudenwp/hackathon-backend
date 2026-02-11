import time
import uuid
from typing import Any

import structlog
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult, TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq.serializers import ORJSONSerializer
from taskiq_redis import (
    ListRedisScheduleSource,
    RedisAsyncResultBackend,
    RedisStreamBroker,
)
from taskiq.abc.broker import AsyncBroker

from src.constants.env import (
    VALKEY_WORKER_URL,
)

# Flag to check if we're in development mode (single worker)
from src.utils.logger import log_error, logger, setup_logging

# Initialize logging for worker processes
setup_logging(json_logs=True, log_level="INFO")


def ensure_cron_tasks_registered():
    """Import all task modules to register them with broker"""
    try:
        # Import all task modules here to ensure they are registered with the broker

        logger.info("All task modules imported successfully")
    except Exception as e:
        logger.error(f"Error importing task modules: {e}")
        raise


class WorkerStartupMiddleware(TaskiqMiddleware):
    """Middleware to execute tasks when worker starts up"""

    async def startup(self) -> None:
        logger.info("Worker startup middleware initializing")

        try:
            # Execute the startup tasks
            from src.tasks.test.test import test_task

            await test_task.kiq()
            # Other startup tasks can be added here
            logger.info("Worker startup tasks completed successfully")
        except Exception as e:
            logger.error(f"Critical: Worker startup tasks failed: {e}")
            # Critical startup failures için worker'ı durdur
            raise SystemExit(f"Worker startup failed: {e}")


class TaskLoggingMiddleware(TaskiqMiddleware):
    async def startup(self) -> None:
        logger.info("TaskiqMiddleware startup")
        # print all tasks
        # logger.info(f"Registered tasks: {list(self.broker.tasks.keys())}")

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        structlog.contextvars.clear_contextvars()

        # Set worker_trace_id for this task execution
        # This allows tracking all logs within the same task
        task_trace_id = message.task_id or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(
            worker_trace_id=task_trace_id,
            task_name=message.task_name,
        )

        # Store start time in message labels for duration calculation
        message.labels["task_start_time"] = time.time()

        # Log task start
        logger.info(
            "Task started",
            task_args=message.args,
            task_kwargs=message.kwargs,
        )
        return message

    async def post_execute(self, message: TaskiqMessage, result: Any) -> Any:
        # Calculate execution duration
        start_time = message.labels.get("task_start_time", time.time())
        duration = time.time() - start_time

        # Log successful completion
        logger.info(
            "Task completed successfully",
            duration_seconds=round(duration, 2),
            result_preview=str(result)[:200] if result else None,
        )

        # Convert result to a dictionary if it's an instance of TaskiqResult
        # result_dict = result.dict() if hasattr(result, "dict") else result

        # Log task details to the database
        # async for db in get_session():
        #     db.add(
        #         TaskiqLog(
        #             task_id=message.task_id,
        #             task_name=message.task_name,
        #             args=json.dumps(message.args),  # Convert args to JSON
        #             kwargs=json.dumps(message.kwargs),  # Convert kwargs to JSON
        #             status="success",
        #             result=result_dict,  # Ensure result is a dictionary
        #         )
        #     )
        #     await db.commit()
        return result

    async def on_error(
        self,
        message: TaskiqMessage,
        result: "TaskiqResult[Any]",
        exception: Exception,
    ) -> None:
        # Calculate execution duration even for failed tasks
        start_time = message.labels.get("task_start_time", time.time())
        duration = time.time() - start_time

        # Log error details
        logger.error(
            "Task failed",
            duration_seconds=round(duration, 2),
            error_message=str(exception),
            error_type=type(exception).__name__,
            result=str(result)[:200] if result else None,
            exc_info=True,
        )

        # Convert result to a dictionary if it's an instance of TaskiqResult
        # result_dict = result.dict() if hasattr(result, "dict") else result

        # Log task failure details to the database
        # async for db in get_session():
        #     db.add(
        #         TaskiqLog(
        #             task_id=message.task_id,
        #             task_name=message.task_name,
        #             args=json.dumps(message.args),  # Convert args to JSON
        #             kwargs=json.dumps(message.kwargs),  # Convert kwargs to JSON
        #             status="failed",
        #             result=result_dict,  # Ensure result is a dictionary
        #         )
        #     )
        #     await db.commit()

    async def post_save(self, message: TaskiqMessage, result: Any) -> None:
        pass


# =============================================================================
# Redis Database Separation (Cost-Free Stream Isolation)
# =============================================================================
# Database allocation is managed in src/constants/env.py:
#   DB 0: HIGH Priority Broker (Chatbot, real-time tasks)
#   DB 1: LOW Priority Broker (Background, cron, integrations)
#   DB 2: Feature Flags Cache
#   DB 3: API Specs Cache
#   DB 4: Taskiq Result Backend
# =============================================================================

# =============================================================================
# Shared Result Backend
# =============================================================================
try:
    result_backend = RedisAsyncResultBackend(
        redis_url=VALKEY_WORKER_URL,
        result_ex_time=60,
    )
    logger.info("Result backend initialized (DB 4)")
except Exception as e:
    log_error(logger, "Result backend creation failed", e)
    raise


# =============================================================================
# Broker Configuration Helper
# =============================================================================
def create_broker(url: str) -> RedisStreamBroker:
    """Create and configure a RedisStreamBroker instance."""
    try:
        # Initialize broker
        b = RedisStreamBroker(url=url)
        b.serializer = ORJSONSerializer()

        # Add middlewares
        b.add_middlewares(WorkerStartupMiddleware(), TaskLoggingMiddleware())
        return b
    except Exception as e:
        log_error(logger, "Broker creation failed", e)
        raise


broker = create_broker(VALKEY_WORKER_URL)


# =============================================================================
# Broker Instances
# =============================================================================


# =============================================================================
# Export Configuration
# =============================================================================
# 'broker' is the default export used by decorators (@broker.task)
# and by the generic worker entrypoint.

try:
    redis_schedule_source = ListRedisScheduleSource(url=VALKEY_WORKER_URL)
    logger.info("Redis schedule source initialized (DB 1)")
except Exception as e:
    log_error(
        logger,
        "Taskiq Redis schedule source creation failed",
        e,
        component="taskiq_redis_schedule",
    )
    raise


# =============================================================================
# Routing Broker (Proxy for Scheduler)
# =============================================================================


class RoutingBroker(AsyncBroker):
    """
    A proxy broker that routes tasks to the appropriate broker (High or Low)
    based on where the task is registered.
    """

    def __init__(
        self,
        broker: AsyncBroker,
    ) -> None:
        super().__init__()
        self.broker = broker

    async def startup(self) -> None:
        # In DEVELOPMENT mode, all brokers point to the same instance
        # Use a set to get unique broker instances and avoid duplicate startup calls
        await self.broker.startup()

    async def shutdown(self) -> None:
        # In DEVELOPMENT mode, all brokers point to the same instance
        # Use a set to get unique broker instances and avoid duplicate shutdown calls
        await self.broker.shutdown()

    async def kick(self, message: TaskiqMessage) -> None:
        # Check if the task is known to the high priority broker
        # We check both custom task names and potentially decorated tasks
        if message.task_name in self.broker.tasks:
            await self.broker.kick(message)

    def register_task(self, task: Any, task_name: str, **kwargs: Any) -> Any:
        # We don't really register tasks on the routing broker itself in this context,
        # but for completeness, we can delegate or just pass.
        # The scheduler uses the broker to kick tasks found in sources.
        return self.broker.register_task(task, task_name, **kwargs)

    async def listen(self) -> None:
        # The scheduler process doesn't listen for tasks, so this might not be called.
        # But if it were, we wouldn't want to listen on two brokers here simultaneously
        # without complex management. For scheduler usage, this is a no-op or delegates.
        pass


scheduler_broker = RoutingBroker(broker=broker)
logger.info("Scheduler RoutingBroker initialized for multi-priority dispatch")

scheduler = TaskiqScheduler(
    scheduler_broker,
    [
        redis_schedule_source,
        LabelScheduleSource(broker),
    ],
)

# Import scheduled tasks AFTER broker and scheduler are created
ensure_cron_tasks_registered()
