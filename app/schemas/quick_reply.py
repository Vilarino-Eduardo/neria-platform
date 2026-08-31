import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QuickReplyCreate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    shortcut: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_-]+$")
    content: str = Field(min_length=1, max_length=5000)

    @field_validator("shortcut")
    @classmethod
    def normalize_shortcut(cls, value: str) -> str:
        return value.strip().lower().removeprefix("/")


class QuickReplyUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=120)
    shortcut: str | None = Field(default=None, min_length=1, max_length=40, pattern=r"^[a-z0-9_-]+$")
    content: str | None = Field(default=None, min_length=1, max_length=5000)
    is_active: bool | None = None

    @field_validator("shortcut")
    @classmethod
    def normalize_shortcut(cls, value: str | None) -> str | None:
        return value.strip().lower().removeprefix("/") if value else value


class QuickReplyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    shortcut: str
    content: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
