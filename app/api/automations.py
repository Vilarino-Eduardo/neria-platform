import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.core import Automation, AutomationSession, AutomationStatus, UserRole
from app.schemas.automation import AutomationCreate, AutomationResponse, AutomationUpdate

router = APIRouter(prefix="/automations", tags=["automations"])


def require_admin(current_user: CurrentUser) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem configurar automações.")


def get_automation(
    session: DatabaseSession, organization_id: uuid.UUID, automation_id: uuid.UUID
) -> Automation:
    automation = session.scalar(
        select(Automation).where(
            Automation.id == automation_id,
            Automation.organization_id == organization_id,
        )
    )
    if automation is None:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    return automation


@router.get("", response_model=list[AutomationResponse])
def list_automations(
    session: DatabaseSession, current_user: CurrentUser
) -> list[Automation]:
    return list(
        session.scalars(
            select(Automation)
            .where(Automation.organization_id == current_user.organization_id)
            .order_by(Automation.created_at)
        )
    )


@router.post("", response_model=AutomationResponse, status_code=status.HTTP_201_CREATED)
def create_automation(
    payload: AutomationCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Automation:
    require_admin(current_user)
    automation = Automation(
        organization_id=current_user.organization_id,
        name=payload.name,
        trigger_keywords=payload.trigger_keywords,
        is_fallback=payload.is_fallback,
        definition=payload.definition.model_dump(),
    )
    session.add(automation)
    session.commit()
    session.refresh(automation)
    return automation


@router.patch("/{automation_id}", response_model=AutomationResponse)
def update_automation(
    automation_id: uuid.UUID,
    payload: AutomationUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Automation:
    require_admin(current_user)
    automation = get_automation(session, current_user.organization_id, automation_id)
    changes = payload.model_dump(exclude_unset=True)
    if "definition" in changes:
        changes["definition"] = payload.definition.model_dump()
        automation.version += 1
        session.execute(
            update(AutomationSession)
            .where(AutomationSession.automation_id == automation.id)
            .values(is_active=False)
        )
    for field, value in changes.items():
        setattr(automation, field, value)
    automation.status = AutomationStatus.DRAFT
    session.commit()
    session.refresh(automation)
    return automation


@router.post("/{automation_id}/activate", response_model=AutomationResponse)
def activate_automation(
    automation_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Automation:
    require_admin(current_user)
    automation = get_automation(session, current_user.organization_id, automation_id)
    if automation.is_fallback:
        session.execute(
            update(Automation)
            .where(
                Automation.organization_id == current_user.organization_id,
                Automation.is_fallback.is_(True),
                Automation.id != automation.id,
            )
            .values(status=AutomationStatus.INACTIVE)
        )
    automation.status = AutomationStatus.ACTIVE
    session.commit()
    session.refresh(automation)
    return automation


@router.post("/{automation_id}/deactivate", response_model=AutomationResponse)
def deactivate_automation(
    automation_id: uuid.UUID,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> Automation:
    require_admin(current_user)
    automation = get_automation(session, current_user.organization_id, automation_id)
    automation.status = AutomationStatus.INACTIVE
    session.execute(
        update(AutomationSession)
        .where(AutomationSession.automation_id == automation.id)
        .values(is_active=False)
    )
    session.commit()
    session.refresh(automation)
    return automation
