import app.models  # noqa: F401
from app.database.base import Base


def test_core_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "contacts",
        "conversations",
        "messages",
        "organizations",
        "organization_profiles",
        "password_reset_tokens",
        "subscriptions",
        "quick_replies",
        "tags",
        "conversation_tags",
        "conversation_events",
        "tickets",
        "users",
        "whatsapp_accounts",
        "whatsapp_templates",
        "whatsapp_webhook_events",
        "automations",
        "automation_sessions",
        "knowledge_sources",
        "knowledge_chunks",
        "ai_configurations",
        "audit_logs",
        "ai_runs",
        "ai_usage_daily",
        "ai_feedback",
        "knowledge_suggestions",
    }
