import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.core import AIFeedbackRating, KnowledgeSuggestionStatus


class AIConfigurationUpdate(BaseModel):
    is_enabled: bool | None = None
    tone: str | None = Field(default=None, min_length=2, max_length=40)
    instructions: str | None = Field(default=None, max_length=5000)
    fallback_message: str | None = Field(default=None, min_length=10, max_length=1000)
    history_message_limit: int | None = Field(default=None, ge=4, le=30)
    retrieval_limit: int | None = Field(default=None, ge=1, le=10)
    minimum_confidence: int | None = Field(default=None, ge=0, le=100)

    @field_validator("tone")
    @classmethod
    def normalize_tone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Informe um tom de voz válido.")
        return normalized


class AIConfigurationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    is_enabled: bool
    tone: str
    instructions: str | None
    fallback_message: str
    history_message_limit: int
    retrieval_limit: int
    minimum_confidence: int


class AISimulationRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class AISimulationSource(BaseModel):
    title: str
    content: str
    score: float


class AISimulationResponse(BaseModel):
    answer: str
    confidence: int
    should_handoff: bool
    route: str
    reason: str
    would_use_paid_provider: bool
    external_request_made: bool = False
    sources: list[AISimulationSource]


class AIDailyUsagePoint(BaseModel):
    date: date
    paid_requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


class AIMetricsResponse(BaseModel):
    period_days: int
    total_runs: int
    completed_runs: int
    escalated_runs: int
    failed_runs: int
    average_confidence: int | None
    handoff_rate: float
    helpful_feedback: int
    correction_feedback: int
    paid_requests_today: int
    daily_request_limit: int
    daily_requests_remaining: int
    daily_quota_percent: int
    daily_quota_status: str
    daily_input_tokens: int
    daily_output_tokens: int
    daily_total_tokens: int
    daily_usage: list[AIDailyUsagePoint]


class AIFeedbackCreate(BaseModel):
    rating: AIFeedbackRating
    correction: str | None = Field(default=None, min_length=10, max_length=5000)

    @model_validator(mode="after")
    def require_correction_when_unhelpful(self):
        if self.rating == AIFeedbackRating.UNHELPFUL and not self.correction:
            raise ValueError("Informe a resposta correta para ensinar a Neria.")
        return self


class AIFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ai_run_id: uuid.UUID
    rating: AIFeedbackRating
    correction: str | None
    created_at: datetime


class KnowledgeSuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ai_run_id: uuid.UUID | None
    question: str
    suggested_content: str
    status: KnowledgeSuggestionStatus
    created_at: datetime
    updated_at: datetime
