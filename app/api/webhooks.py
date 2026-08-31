import hashlib
import hmac
import uuid

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request
from sqlalchemy import select

from app.api.dependencies import DatabaseSession
from app.core.settings import get_settings
from app.integrations.whatsapp.processor import process_webhook_event
from app.models.core import WebhookEventStatus, WhatsAppWebhookEvent

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
    background_tasks: BackgroundTasks,
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
            session.commit()
            background_tasks.add_task(process_event_in_background, existing.id)
            return {"status": "retried"}
        return {"status": "duplicate"}

    event = WhatsAppWebhookEvent(payload_hash=payload_hash, payload=await request.json())
    session.add(event)
    session.commit()
    session.refresh(event)

    background_tasks.add_task(process_event_in_background, event.id)
    return {"status": "accepted"}


def process_event_in_background(event_id: uuid.UUID) -> None:
    from app.database.session import SessionLocal

    with SessionLocal() as session:
        event = session.get(WhatsAppWebhookEvent, event_id)
        if event:
            process_webhook_event(session, event)
