import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_name: str | None
    action: str
    target_type: str | None
    target_id: str | None
    metadata: dict
    created_at: datetime
