from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.models.core import (
    AIConfiguration,
    Automation,
    AutomationStatus,
    KnowledgeSource,
    KnowledgeSourceStatus,
    OrganizationProfile,
    UserRole,
    WhatsAppAccount,
    WhatsAppAccountStatus,
)
from app.schemas.onboarding import OnboardingResponse, OnboardingStepResponse

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("", response_model=OnboardingResponse)
def get_onboarding(
    session: DatabaseSession, current_user: CurrentUser
) -> OnboardingResponse:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Apenas administradores acessam o onboarding.")
    organization_id = current_user.organization_id
    profile = session.scalar(
        select(OrganizationProfile).where(
            OrganizationProfile.organization_id == organization_id
        )
    )
    profile_ready = bool(
        profile
        and profile.description
        and (profile.contact_phone or profile.contact_email)
        and profile.opening_hours
    )
    whatsapp_ready = bool(
        session.scalar(
            select(func.count(WhatsAppAccount.id)).where(
                WhatsAppAccount.organization_id == organization_id,
                WhatsAppAccount.status == WhatsAppAccountStatus.ACTIVE,
            )
        )
    )
    knowledge_ready = bool(
        session.scalar(
            select(func.count(KnowledgeSource.id)).where(
                KnowledgeSource.organization_id == organization_id,
                KnowledgeSource.status == KnowledgeSourceStatus.READY,
            )
        )
    )
    automation_ready = bool(
        session.scalar(
            select(func.count(Automation.id)).where(
                Automation.organization_id == organization_id,
                Automation.status == AutomationStatus.ACTIVE,
            )
        )
    )
    ai_ready = session.scalar(
        select(AIConfiguration.id).where(AIConfiguration.organization_id == organization_id)
    ) is not None
    steps = [
        OnboardingStepResponse(key="company", title="Complete os dados da empresa", description="Informe contato, descrição e horários.", section="settings", completed=profile_ready, required=True),
        OnboardingStepResponse(key="whatsapp", title="Conecte o WhatsApp", description="Cadastre e valide o número da empresa.", section="whatsapp", completed=whatsapp_ready, required=True),
        OnboardingStepResponse(key="knowledge", title="Adicione conhecimento", description="Inclua ao menos uma informação ou documento.", section="knowledge", completed=knowledge_ready, required=True),
        OnboardingStepResponse(key="automation", title="Ative uma automação", description="Configure o primeiro fluxo de atendimento.", section="automations", completed=automation_ready, required=True),
        OnboardingStepResponse(key="ai", title="Prepare a inteligência", description="Ajuste tom, segurança e mensagem de transferência.", section="ai", completed=ai_ready, required=False),
    ]
    required = [step for step in steps if step.required]
    completed = sum(step.completed for step in required)
    return OnboardingResponse(
        completed_required=completed,
        total_required=len(required),
        progress_percent=round(completed / len(required) * 100),
        is_complete=completed == len(required),
        steps=steps,
    )
