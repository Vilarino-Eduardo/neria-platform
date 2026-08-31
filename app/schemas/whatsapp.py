import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.core import WhatsAppAccountStatus, WhatsAppTemplateStatus


class WhatsAppAccountCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=160)
    phone_number: str = Field(min_length=8, max_length=32)
    meta_phone_number_id: str = Field(min_length=2, max_length=64)
    meta_business_account_id: str = Field(min_length=2, max_length=64)
    access_token: str = Field(min_length=20, max_length=2000)


class WhatsAppAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    display_name: str
    phone_number: str
    meta_phone_number_id: str | None
    meta_business_account_id: str | None
    status: WhatsAppAccountStatus
    is_primary: bool


class WhatsAppTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    whatsapp_account_id: uuid.UUID
    name: str
    language: str
    category: str | None
    status: WhatsAppTemplateStatus
