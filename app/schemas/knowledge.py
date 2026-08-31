import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.core import KnowledgeSourceStatus, KnowledgeSourceType


class ManualKnowledgeCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    content: str = Field(min_length=20, max_length=2_000_000)


class KnowledgeSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    source_type: KnowledgeSourceType
    status: KnowledgeSourceStatus
    filename: str | None
    mime_type: str | None
    character_count: int
    error: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    content: str
    chunk_metadata: dict
