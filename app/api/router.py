from fastapi import APIRouter

from app.api.ai import router as ai_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.automations import router as automations_router
from app.api.billing import router as billing_router
from app.api.contacts import router as contacts_router
from app.api.conversations import router as conversations_router
from app.api.dashboard import router as dashboard_router
from app.api.exports import router as exports_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router
from app.api.notifications import router as notifications_router
from app.api.onboarding import router as onboarding_router
from app.api.organization import router as organization_router
from app.api.privacy import router as privacy_router
from app.api.quick_replies import router as quick_replies_router
from app.api.tags import router as tags_router
from app.api.tickets import router as tickets_router
from app.api.users import router as users_router
from app.api.webhooks import router as webhooks_router
from app.api.whatsapp_accounts import router as whatsapp_accounts_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(knowledge_router)
api_router.include_router(notifications_router)
api_router.include_router(onboarding_router)
api_router.include_router(auth_router)
api_router.include_router(ai_router)
api_router.include_router(audit_router)
api_router.include_router(billing_router)
api_router.include_router(automations_router)
api_router.include_router(users_router)
api_router.include_router(organization_router)
api_router.include_router(privacy_router)
api_router.include_router(quick_replies_router)
api_router.include_router(contacts_router)
api_router.include_router(conversations_router)
api_router.include_router(dashboard_router)
api_router.include_router(exports_router)
api_router.include_router(tickets_router)
api_router.include_router(tags_router)
api_router.include_router(whatsapp_accounts_router)
api_router.include_router(webhooks_router)
