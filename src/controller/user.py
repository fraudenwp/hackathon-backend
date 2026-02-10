from typing import Annotated

from fastapi import APIRouter, Depends, Form, Security, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud.auth import AuthCRUD
from src.crud.user import UserCRUD

from src.models.sqlmodels.user import User
from src.models.dependency import get_session


class UserController:
    tags = ["user"]
    router = APIRouter(tags=tags)

    @staticmethod
    @router.post("/create/", response_model=User, status_code=status.HTTP_200_OK)
    async def create_user(
        username: str = Form(...),
        password: str = Form(...),
        db: AsyncSession = Depends(get_session),
    ):
        return await UserCRUD.create(username, password, db)

    @staticmethod
    @router.get("/user/{user_id}", response_model=User, status_code=status.HTTP_200_OK)
    async def get_user(user_id: str, db: AsyncSession = Depends(get_session)):
        return await UserCRUD.get_by_id(user_id, db)

    @staticmethod
    @router.get("/me/", response_model=User, status_code=status.HTTP_200_OK)
    async def read_user_me(
        current_user: Annotated[
            User,
            Security(
                AuthCRUD.get_current_user_with_access(),
            ),
        ],
        db: AsyncSession = Depends(get_session),
    ):
        return await UserCRUD.get_me(current_user, db)
