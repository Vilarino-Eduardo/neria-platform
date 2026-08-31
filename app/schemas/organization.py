import uuid

from pydantic import BaseModel, ConfigDict, Field


class OrganizationProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    company_name: str
    description: str | None
    contact_phone: str | None
    contact_email: str | None
    address: str | None
    opening_hours: str | None
    welcome_message: str
    primary_color: str | None
    logo_url: str | None
    sla_first_response_minutes: int
    auto_assignment_enabled: bool
    data_retention_days: int


class UpdateOrganizationProfileRequest(BaseModel):
    company_name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    contact_phone: str | None = Field(default=None, max_length=32)
    contact_email: str | None = Field(default=None, max_length=320)
    address: str | None = Field(default=None, max_length=500)
    opening_hours: str | None = Field(default=None, max_length=500)
    welcome_message: str | None = Field(default=None, min_length=1, max_length=2000)
    primary_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    logo_url: str | None = Field(default=None, max_length=500)
    sla_first_response_minutes: int | None = Field(default=None, ge=1, le=1440)
    auto_assignment_enabled: bool | None = None
    data_retention_days: int | None = Field(default=None, ge=30, le=3650)
