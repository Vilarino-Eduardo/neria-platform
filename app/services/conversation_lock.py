import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_active_conversation(
    session: Session,
    organization_id: uuid.UUID,
    whatsapp_account_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> None:
    """Serialize creation of the active conversation for one contact/account."""
    lock_key = f"{organization_id}:{whatsapp_account_id}:{contact_id}"
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": lock_key},
    )
