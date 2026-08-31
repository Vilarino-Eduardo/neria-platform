import hashlib
import uuid

from sqlalchemy.orm import Session

from app.models.core import AuditLog


def record_audit(
    session: Session,
    *,
    organization_id: uuid.UUID,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    event = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        event_metadata=metadata or {},
        ip_hash=(hashlib.sha256(ip_address.encode()).hexdigest() if ip_address else None),
    )
    session.add(event)
    return event
