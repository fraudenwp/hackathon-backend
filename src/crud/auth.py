import random
import string
from datetime import datetime, timedelta
from typing import Annotated, Optional

from fastapi import Depends, HTTPException
from fastapi.security import (
    OAuth2PasswordRequestForm,
)
from jose import JWTError, jwt
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from src.constants.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    oauth2_scheme,
    pwd_context,
)
from src.constants.env import (
    SECRET_KEY,
)
from src.crud.user import UserCRUD
from src.models.basemodels.user import (
    AccessToken,
    TokenData,
)
from src.models.sqlmodels.user import User
from src.models.dependency import get_session


class AuthCRUD:
    @staticmethod
    def get_password_hash(password):
        return pwd_context.hash(password)

    @staticmethod
    def create_access_token(data: dict, expires_delta: timedelta | None = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    @staticmethod
    def verify_password(plain_password, hashed_password):
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    async def authenticate_user(identifier: str, password: str, db: AsyncSession):
        user = await UserCRUD.get_by_username(identifier, db)
        if not user:
            return False
        if not AuthCRUD.verify_password(password, user.hashed_password):
            return False
        return user

    @staticmethod
    async def signin(
        form_data: OAuth2PasswordRequestForm,
        db: AsyncSession,
    ) -> AccessToken:
        user = await AuthCRUD.authenticate_user(
            form_data.username, form_data.password, db
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = AuthCRUD.create_access_token(
            data={"sub": user.username},
            expires_delta=access_token_expires,
        )
        return AccessToken(
            access_token=access_token,
            token_type="Bearer",
        )

    @staticmethod
    def get_current_user_with_access():
        async def dependency(
            token: Annotated[str, Depends(oauth2_scheme)],
            db: AsyncSession = Depends(get_session),
        ):
            return await AuthCRUD.get_current_user(
                token=token,
                db=db,
            )

        return dependency

    @staticmethod
    def get_current_user_optional():
        """
        Opsiyonel kullanıcı authentication.
        Token varsa kullanıcı döner, yoksa None döner.
        Feed gibi hem giriş yapmış hem yapmamış kullanıcılara açık endpointler için.
        """
        from fastapi.security import OAuth2PasswordBearer

        oauth2_scheme_optional = OAuth2PasswordBearer(
            tokenUrl="auth/login",
            auto_error=False,
        )

        async def dependency(
            token: Optional[str] = Depends(oauth2_scheme_optional),
            db: AsyncSession = Depends(get_session),
        ) -> Optional[User]:
            if not token:
                return None

            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                username: str = payload.get("sub")
                if username is None:
                    return None
                user = await UserCRUD.get_by_username(username, db)
                return user
            except (JWTError, ValidationError):
                return None

        return dependency

    @staticmethod
    async def get_current_user(
        token: Annotated[str, Depends(oauth2_scheme)],
        db: AsyncSession = Depends(get_session),
    ):
        from src.crud.user import UserCRUD

        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise credentials_exception
            token_data = TokenData(username=username)
        except (JWTError, ValidationError):
            raise credentials_exception
        user = await UserCRUD.get_by_username(token_data.username, db)
        if user is None:
            raise credentials_exception
        return user

    @staticmethod
    def generate_random_password(
        length: int = 12,
        letters: bool = True,
        digits: bool = True,
        punctuation: bool = True,
    ) -> str:
        characters = ""
        if letters:
            characters += string.ascii_letters
        if digits:
            characters += string.digits
        if punctuation:
            characters += string.punctuation

        if not characters:
            raise ValueError("At least one character set must be enabled")

        password = "".join(random.choices(characters, k=length))
        return password
