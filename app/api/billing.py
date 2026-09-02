import hmac
import uuid

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select

from app.api.dependencies import AuthenticatedUser, DatabaseSession
from app.core.settings import get_settings
from app.models.core import Organization, Subscription
from app.schemas.billing import ManualSubscriptionUpdate, SubscriptionResponse
from app.services.audit import record_audit

router = APIRouter(prefix="/billing", tags=["billing"])


def subscription_response(subscription: Subscription, max_users: int) -> dict:
    return {
        "id": subscription.id,
        "organization_id": subscription.organization_id,
        "plan_code": subscription.plan_code,
        "status": subscription.status,
        "trial_ends_at": subscription.trial_ends_at,
        "current_period_ends_at": subscription.current_period_ends_at,
        "max_users": max_users,
        "ai_daily_request_limit": subscription.ai_daily_request_limit,
        "ai_daily_token_limit": subscription.ai_daily_token_limit,
    }


@router.get("/subscription", response_model=SubscriptionResponse)
def get_subscription(
    session: DatabaseSession, current_user: AuthenticatedUser
) -> dict:
    subscription = session.scalar(
        select(Subscription).where(
            Subscription.organization_id == current_user.organization_id
        )
    )
    organization = session.get(Organization, current_user.organization_id)
    if subscription is None or organization is None:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada.")
    return subscription_response(subscription, organization.max_users)


@router.patch(
    "/internal/organizations/{organization_id}",
    response_model=SubscriptionResponse,
)
def update_subscription_manually(
    organization_id: uuid.UUID,
    payload: ManualSubscriptionUpdate,
    session: DatabaseSession,
    billing_admin_key: str | None = Header(default=None, alias="X-Billing-Admin-Key"),
) -> dict:
    expected = get_settings().billing_admin_key
    if not expected or not billing_admin_key or not hmac.compare_digest(expected, billing_admin_key):
        raise HTTPException(status_code=403, detail="Credencial administrativa inválida.")
    organization = session.get(Organization, organization_id)
    subscription = session.scalar(
        select(Subscription).where(Subscription.organization_id == organization_id)
    )
    if organization is None or subscription is None:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada.")
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(subscription, field, value)
    record_audit(
        session,
        organization_id=organization_id,
        action="billing.subscription_updated",
        target_type="subscription",
        target_id=str(subscription.id),
        metadata={"status": subscription.status.value, "plan_code": subscription.plan_code},
    )
    session.commit()
    session.refresh(subscription)
    return subscription_response(subscription, organization.max_users)
