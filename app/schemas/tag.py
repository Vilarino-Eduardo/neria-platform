import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str
    created_at: datetime
    updated_at: datetime
