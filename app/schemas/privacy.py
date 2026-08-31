import uuid

from pydantic import BaseModel, Field


class PrivacyConfirmation(BaseModel):
    confirmation: str = Field(min_length=5, max_length=20)


class RetentionPreviewResponse(BaseModel):
    retention_days: int
    cutoff: str
    conversations_eligible: int


class RetentionRunResponse(RetentionPreviewResponse):
    conversations_sanitized: int


class ContactAnonymizationResponse(BaseModel):
    contact_id: uuid.UUID
    conversations_sanitized: int
    messages_sanitized: int
