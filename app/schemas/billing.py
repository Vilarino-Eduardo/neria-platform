import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.core import SubscriptionStatus


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    plan_code: str
    status: SubscriptionStatus
    trial_ends_at: datetime | None
    current_period_ends_at: datetime | None
    max_users: int
    ai_daily_request_limit: int
    ai_daily_token_limit: int


class ManualSubscriptionUpdate(BaseModel):
    status: SubscriptionStatus
    plan_code: str | None = Field(default=None, min_length=2, max_length=40)
    current_period_ends_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)
    ai_daily_request_limit: int | None = Field(default=None, ge=0, le=100_000)
    ai_daily_token_limit: int | None = Field(default=None, ge=0, le=100_000_000)
