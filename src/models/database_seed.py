from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import db
from src.models.seed_initials import seed_initials
from src.utils.logger import logger


async def seed_system(session: AsyncSession):
    print("Seeding system...")
    try:
        await seed_initials(session)
    except Exception as e:
        logger.error(f"Error seeding system: {e}")

    print("System seeded.")


async def seed_db():
    async with db.get_session_context() as session:
        try:
            await seed_system(session)
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()
