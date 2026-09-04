"""harden webhook processing

Revision ID: 6d8f2a91c4be
Revises: c61a82f4d207
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6d8f2a91c4be"
down_revision: str | Sequence[str] | None = "c61a82f4d207"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_webhook_events",
        sa.Column("processing_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "whatsapp_webhook_events",
        sa.Column("processing_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("whatsapp_webhook_events", "payload", nullable=True)
    op.execute(
        "UPDATE whatsapp_webhook_events SET payload = NULL WHERE status = 'PROCESSED'"
    )
    op.alter_column("whatsapp_webhook_events", "processing_attempts", server_default=None)
    op.create_index(
        "uq_conversations_active_contact_account",
        "conversations",
        ["organization_id", "whatsapp_account_id", "contact_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'CLOSED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_conversations_active_contact_account", table_name="conversations")
    op.execute(
        "UPDATE whatsapp_webhook_events SET payload = '{}'::jsonb WHERE payload IS NULL"
    )
    op.alter_column("whatsapp_webhook_events", "payload", nullable=False)
    op.drop_column("whatsapp_webhook_events", "processing_claimed_at")
    op.drop_column("whatsapp_webhook_events", "processing_attempts")
