from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.config import pwd_context

from src.models.sqlmodels.user import User

from src.utils.logger import logger


class UserCRUD:
    @staticmethod
    def get_password_hash(password):
        return pwd_context.hash(password)

    @staticmethod
    async def create(
        username: str,
        password: str,
        db: AsyncSession,
    ):
        try:
            new_user = User(
                username=username,
                hashed_password=UserCRUD.get_password_hash(password),
            )
            db.add(new_user)
            new_user.disabled = False
            await db.commit()
            return new_user
        except Exception as e:
            await db.rollback()
            # Check if it's a unique constraint violation
            if (
                "UniqueViolationError" in str(type(e))
                or "unique constraint" in str(e).lower()
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Bu kullanıcı adı zaten kullanılıyor",
                )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    @staticmethod
    async def update(user_id: str, user: User, db: AsyncSession):
        stmt = (
            update(User).where(User.id == user_id, User.disabled == False).values(user)  # noqa
        )  # noqa
        await db.execute(stmt)
        await db.commit()
        return user

    @staticmethod
    async def get_by_id(user_id: str, db: AsyncSession):
        query = select(User).where(User.id == user_id, User.disabled == False)  # noqa
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_username(identifier: str, db: AsyncSession):
        result = await db.execute(
            select(User).where(
                (User.username == identifier),
                (User.disabled == False),  # noqa
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_me(user: User, db: AsyncSession):
        try:
            if user.disabled:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="There is no user"
                )
            return user
        except Exception as e:
            logger.error(f"Error getting me: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )
