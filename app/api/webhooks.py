import hashlib
import hmac

from fastapi import APIRouter, Header, HTTPException, Query, Request
from sqlalchemy import select

from app.api.dependencies import DatabaseSession
from app.core.settings import get_settings
from app.models.core import WebhookEventStatus, WhatsAppAccount, WhatsAppWebhookEvent
from app.tasks.webhooks import enqueue_webhook_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/whatsapp")
def verify_whatsapp_webhook(
    mode: str = Query(alias="hub.mode"),
    verify_token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
) -> int:
    settings = get_settings()
    if mode != "subscribe" or not hmac.compare_digest(
        verify_token, settings.meta_webhook_verify_token
    ):
        raise HTTPException(status_code=403, detail="Token de verificação inválido.")
    return int(challenge)


@router.post("/whatsapp", status_code=200)
async def receive_whatsapp_webhook(
    request: Request,
    session: DatabaseSession,
    x_hub_signature_256: str | None = Header(default=None),
) -> dict[str, str]:
    raw_body = await request.body()
    settings = get_settings()
    expected = "sha256=" + hmac.new(
        settings.meta_app_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    if x_hub_signature_256 is None or not hmac.compare_digest(
        x_hub_signature_256, expected
    ):
        raise HTTPException(status_code=401, detail="Assinatura inválida.")

    payload_hash = hashlib.sha256(raw_body).hexdigest()
    existing = session.scalar(
        select(WhatsAppWebhookEvent).where(
            WhatsAppWebhookEvent.payload_hash == payload_hash
        )
    )
    if existing:
        if existing.status == WebhookEventStatus.FAILED:
            existing.status = WebhookEventStatus.PENDING
            existing.error = None
            existing.processed_at = None
            existing.processing_attempts = 0
            session.commit()
            enqueue_webhook_event(str(existing.id))
            return {"status": "retried"}
        return {"status": "duplicate"}

    payload = await request.json()
    phone_number_ids = {
        change.get("value", {}).get("metadata", {}).get("phone_number_id")
        for entry in payload.get("entry", [])
        for change in entry.get("changes", [])
    }
    organization_id = (
        session.scalar(
            select(WhatsAppAccount.organization_id).where(
                WhatsAppAccount.meta_phone_number_id.in_(phone_number_ids)
            )
        )
        if phone_number_ids
        else None
    )
    event = WhatsAppWebhookEvent(
        organization_id=organization_id,
        payload_hash=payload_hash,
        payload=payload,
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    enqueue_webhook_event(str(event.id))
    return {"status": "accepted"}
