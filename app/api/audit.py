from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.core import AuditLog, User, UserRole
from app.schemas.audit import AuditLogResponse

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
    session: DatabaseSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
) -> list[dict]:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem ver a auditoria.")
    actor = aliased(User)
    rows = session.execute(
        select(AuditLog, actor.name.label("actor_name"))
        .outerjoin(actor, actor.id == AuditLog.actor_user_id)
        .where(AuditLog.organization_id == current_user.organization_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": row.AuditLog.id,
            "actor_user_id": row.AuditLog.actor_user_id,
            "actor_name": row.actor_name,
            "action": row.AuditLog.action,
            "target_type": row.AuditLog.target_type,
            "target_id": row.AuditLog.target_id,
            "metadata": row.AuditLog.event_metadata,
            "created_at": row.AuditLog.created_at,
        }
        for row in rows
    ]
