from src.tasks.taskiq_setup import broker
from src.utils.logger import logger


@broker.task
async def test_task():
    logger.info("test_task tamamlandı")
    return "test tamamlandı"
