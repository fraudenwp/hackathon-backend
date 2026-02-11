from typing import Annotated, Union

from fastapi import APIRouter, Depends, Form, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud.auth import AuthCRUD
from src.crud.user import UserCRUD
from src.models.basemodels.user import AccessToken
from src.models.dependency import get_session


class AuthController:
    tags = ["auth"]
    router = APIRouter(tags=tags)

    @staticmethod
    @router.post("/signup/", status_code=status.HTTP_200_OK)
    async def signup(
        username: str = Form(...),
        password: str = Form(...),
        db: AsyncSession = Depends(get_session),
    ):
        user = await UserCRUD.create(username, password, db)
        return user

    @staticmethod
    @router.post(
        "/login", response_model=Union[AccessToken, str], status_code=status.HTTP_200_OK
    )
    async def login_for_access_token(
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
        db: AsyncSession = Depends(get_session),
    ):
        return await AuthCRUD.signin(form_data, db)
