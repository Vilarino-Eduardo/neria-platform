from celery import Celery

from app.core.settings import get_settings

settings = get_settings()
celery_app = Celery(
    "neria",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.whatsapp",
        "app.tasks.ai",
        "app.tasks.webhooks",
        "app.tasks.emails",
        "app.tasks.knowledge",
    ],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Sao_Paulo",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_soft_time_limit=90,
    task_time_limit=120,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    broker_transport_options={"visibility_timeout": 300},
    beat_schedule={
        "recover-pending-whatsapp-messages": {
            "task": "whatsapp.recover_pending_messages",
            "schedule": 30.0,
        },
        "recover-pending-ai-runs": {
            "task": "ai.recover_pending_runs",
            "schedule": 30.0,
        },
        "recover-pending-webhook-events": {
            "task": "webhooks.recover_pending_events",
            "schedule": 30.0,
        },
        "recover-pending-password-reset-emails": {
            "task": "emails.recover_pending_password_resets",
            "schedule": 30.0,
        },
        "recover-processing-knowledge-sources": {
            "task": "knowledge.recover_processing_sources",
            "schedule": 60.0,
        },
    },
)
