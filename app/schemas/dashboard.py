import uuid
from datetime import date

from pydantic import BaseModel

from app.models.core import UserRole


class DailyVolumeResponse(BaseModel):
    date: date
    inbound: int
    outbound: int


class TeamPerformanceResponse(BaseModel):
    user_id: uuid.UUID
    name: str
    role: UserRole
    is_active: bool
    open_assigned: int
    closed_30d: int
    messages_sent_30d: int
    average_response_minutes: float | None


class DashboardResponse(BaseModel):
    open_conversations: int
    waiting_human: int
    messages_today: int
    active_contacts_30d: int
    closed_conversations_30d: int
    average_first_response_minutes: float | None
    sla_overdue: int
    daily_volume: list[DailyVolumeResponse]
    team_performance: list[TeamPerformanceResponse]
