import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.core.password_policy import validate_password_strength
from app.models.core import UserRole

StrongPassword = Annotated[
    str,
    Field(min_length=12, max_length=128),
    AfterValidator(validate_password_strength),
]


class RegisterOrganizationRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=160)
    organization_slug: str = Field(
        min_length=2,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    admin_name: str = Field(min_length=2, max_length=160)
    admin_email: str = Field(min_length=5, max_length=320)
    password: StrongPassword

    @field_validator("admin_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: StrongPassword


class MessageResponse(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    max_users: int


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    email: str
    role: UserRole
    is_active: bool
    accepts_assignments: bool


class RegistrationResponse(BaseModel):
    organization: OrganizationResponse
    user: UserResponse
    token: TokenResponse


class CreateUserRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=320)
    password: StrongPassword
    role: UserRole = UserRole.AGENT

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UpdateUserRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    role: UserRole | None = None
    is_active: bool | None = None
    accepts_assignments: bool | None = None
