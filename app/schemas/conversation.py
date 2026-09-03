import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.models.core import (
    ConversationMode,
    ConversationPriority,
    ConversationStatus,
    MessageDirection,
    MessageStatus,
    MessageType,
    TicketStatus,
)


class ContactCreate(BaseModel):
    phone_number: str = Field(min_length=8, max_length=32)
    name: str | None = Field(default=None, max_length=160)


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    is_blocked: bool | None = None


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    phone_number: str
    name: str | None
    profile_name: str | None
    is_blocked: bool
    anonymized_at: datetime | None
    created_at: datetime


class ConversationCreate(BaseModel):
    whatsapp_account_id: uuid.UUID
    contact_id: uuid.UUID


class ConversationUpdate(BaseModel):
    status: ConversationStatus | None = None
    mode: ConversationMode | None = None
    assigned_user_id: uuid.UUID | None = None
    priority: ConversationPriority | None = None


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    whatsapp_account_id: uuid.UUID
    contact_id: uuid.UUID
    assigned_user_id: uuid.UUID | None
    status: ConversationStatus
    mode: ConversationMode
    priority: ConversationPriority
    last_message_at: datetime | None
    last_customer_message_at: datetime | None
    last_human_response_at: datetime | None
    unread_count: int
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InboxConversationResponse(ConversationResponse):
    contact_name: str
    contact_phone: str
    assigned_user_name: str | None
    last_message_body: str | None
    last_message_direction: MessageDirection | None
    last_message_status: MessageStatus | None
    sla_status: Literal["on_time", "warning", "overdue"] | None
    sla_due_at: datetime | None
    waiting_minutes: int | None


class ConversationNoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class ConversationEventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    content: str | None
    event_data: dict | None
    actor_user_id: uuid.UUID | None
    actor_name: str | None
    created_at: datetime


class ReplyButton(BaseModel):
    id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=20)


class ButtonInteractiveContent(BaseModel):
    kind: Literal["buttons"]
    body: str = Field(min_length=1, max_length=1024)
    footer: str | None = Field(default=None, max_length=60)
    buttons: list[ReplyButton] = Field(min_length=1, max_length=3)


class ListRow(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=24)
    description: str | None = Field(default=None, max_length=72)


class ListSection(BaseModel):
    title: str = Field(min_length=1, max_length=24)
    rows: list[ListRow] = Field(min_length=1, max_length=10)


class ListInteractiveContent(BaseModel):
    kind: Literal["list"]
    body: str = Field(min_length=1, max_length=1024)
    button_text: str = Field(min_length=1, max_length=20)
    footer: str | None = Field(default=None, max_length=60)
    sections: list[ListSection] = Field(min_length=1, max_length=10)


InteractiveContent = Annotated[
    ButtonInteractiveContent | ListInteractiveContent,
    Field(discriminator="kind"),
]


class MessageCreate(BaseModel):
    body: str | None = Field(default=None, min_length=1, max_length=10000)
    message_type: MessageType = MessageType.TEXT
    media_url: HttpUrl | None = None
    media_filename: str | None = Field(default=None, max_length=255)
    interactive: InteractiveContent | None = None
    template_id: uuid.UUID | None = None
    template_parameters: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_content(self):
        if self.message_type == MessageType.TEXT and not self.body:
            raise ValueError("Mensagem de texto requer conteúdo.")
        if (
            self.message_type in {MessageType.IMAGE, MessageType.DOCUMENT, MessageType.AUDIO}
            and self.media_url is None
        ):
            raise ValueError("Mensagem de mídia requer uma URL.")
        if self.message_type == MessageType.INTERACTIVE and self.interactive is None:
            raise ValueError("Mensagem interativa requer botões ou lista.")
        if self.message_type == MessageType.TEMPLATE and self.template_id is None:
            raise ValueError("Mensagem de template requer um template aprovado.")
        return self


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    conversation_id: uuid.UUID
    template_id: uuid.UUID | None
    sender_user_id: uuid.UUID | None
    external_message_id: str | None
    direction: MessageDirection
    message_type: MessageType
    status: MessageStatus
    delivery_attempts: int
    delivery_error: str | None
    body: str | None
    media_id: str | None
    media_url: str | None
    media_mime_type: str | None
    media_filename: str | None
    created_at: datetime
    ai_run_id: uuid.UUID | None = None
    ai_source_titles: list[str] = Field(default_factory=list)


class TicketCreate(BaseModel):
    subject: str | None = Field(default=None, max_length=200)


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    conversation_id: uuid.UUID
    assigned_user_id: uuid.UUID | None
    protocol: str
    status: TicketStatus
    subject: str | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
