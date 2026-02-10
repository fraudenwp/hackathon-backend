import time
import uuid
from typing import Any

import structlog
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult, TaskiqScheduler
from taskiq.serializers import ORJSONSerializer
from taskiq_redis import (
    RedisStreamBroker,
)

from src.constants.env import VALKEY_WORKER_URL
from src.utils.logger import log_error, logger, setup_logging

# Initialize logging for worker processes
setup_logging(json_logs=True, log_level="INFO")



class WorkerStartupMiddleware(TaskiqMiddleware):
    """Middleware to execute tasks when worker starts up"""

    async def startup(self) -> None:
        logger.info("Worker startup middleware initializing")

        try:

            # Execute the startup tasks
            from src.tasks.test.test import (
                test_task,
            )

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


    async def post_save(self, message: TaskiqMessage, result: Any) -> None:
        pass


# =============================================================================
# Broker Configuration
# =============================================================================
def create_broker(url: str) -> RedisStreamBroker:
    """Create and configure a RedisStreamBroker instance."""
    try:
        # Initialize broker
        b = RedisStreamBroker(url=url)
        b.serializer = ORJSONSerializer()

        # Add middlewares
        middlewares = [
            WorkerStartupMiddleware(),
            TaskLoggingMiddleware(),
        ]
        b.add_middlewares(*middlewares)
        return b
    except Exception as e:
        log_error(logger, "Broker creation failed", e, {"url": url})
        raise


# =============================================================================
# Broker Instance
# =============================================================================
broker = create_broker(VALKEY_WORKER_URL)
logger.info("Single broker initialized")

