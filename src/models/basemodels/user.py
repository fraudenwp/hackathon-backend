import re
from typing import Optional

from pydantic import BaseModel


class ResponseBase(BaseModel):
    total_count: int
    skip: int
    limit: int

    class Config:
        arbitrary_types_allowed = True
        from_attributes = True


class UserResponse(BaseModel):
    id: str
    username: str


class AccessToken(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str


class TokenData(BaseModel):
    username: Optional[str]


class PasswordValidator:
    @staticmethod
    def validate(password: str) -> tuple[bool, Optional[str]]:
        """Password validation rules"""
        rules = [
            (len(password) >= 8, "Password must be at least 8 characters long"),
            (len(password) <= 40, "Password must be at most 40 characters long"),
            (
                bool(re.search(r"[A-ZŞİĞÜÖÇ]", password)),
                "Password must contain at least one uppercase letter",
            ),
            (
                bool(re.search(r"[a-zşığüöç]", password)),
                "Password must contain at least one lowercase letter",
            ),
            (
                bool(re.search(r"[0-9]", password)),
                "Password must contain at least one number",
            ),
            (
                bool(re.search(r"[!@#$%^&*(),.?\":{}|<>]", password)),
                "Password must contain at least one special character",
            ),
        ]

        for is_valid, message in rules:
            if not is_valid:
                return False, message

        return True, None
