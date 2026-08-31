from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.core import OrganizationProfile, UserRole
from app.schemas.organization import (
    OrganizationProfileResponse,
    UpdateOrganizationProfileRequest,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/organization", tags=["organization"])


@router.get("/profile", response_model=OrganizationProfileResponse)
def get_profile(
    session: DatabaseSession,
    current_user: CurrentUser,
) -> OrganizationProfile:
    profile = session.scalar(
        select(OrganizationProfile).where(
            OrganizationProfile.organization_id == current_user.organization_id
        )
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Perfil da empresa não encontrado.")
    return profile


@router.patch("/profile", response_model=OrganizationProfileResponse)
def update_profile(
    payload: UpdateOrganizationProfileRequest,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> OrganizationProfile:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores podem editar a empresa.")

    profile = session.scalar(
        select(OrganizationProfile).where(
            OrganizationProfile.organization_id == current_user.organization_id
        )
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Perfil da empresa não encontrado.")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(profile, field, value)

    record_audit(
        session,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        action="organization.profile_updated",
        target_type="organization_profile",
        target_id=str(profile.id),
        metadata={"fields": sorted(changes)},
    )

    session.commit()
    session.refresh(profile)
    return profile
