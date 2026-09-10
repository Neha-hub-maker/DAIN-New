import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.dain import UserRole


class RegistrationRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    department: str | None = Field(default=None, max_length=150)

    @field_validator("password")
    @classmethod
    def password_must_not_be_whitespace(cls, value: str) -> str:
        if value.isspace():
            raise ValueError("Password must not contain only whitespace.")
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    department: str | None
    role: UserRole
    is_email_verified: bool
    is_active: bool
    created_at: datetime


class RegistrationResponse(BaseModel):
    user: UserResponse
    message: str
    verification_token: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse


class EmailVerificationRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class MessageResponse(BaseModel):
    message: str
