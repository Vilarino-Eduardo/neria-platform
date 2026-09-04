"""scope webhook privacy

Revision ID: 7a3c9d10e5f2
Revises: 6d8f2a91c4be
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a3c9d10e5f2"
down_revision: str | Sequence[str] | None = "6d8f2a91c4be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_webhook_events",
        sa.Column("organization_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_whatsapp_webhook_events_organization_id_organizations",
        "whatsapp_webhook_events",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_whatsapp_webhook_events_organization_id",
        "whatsapp_webhook_events",
        ["organization_id"],
    )
    # Historical events predate tenant scoping and cannot be attributed reliably.
    # Discard their raw payload instead of retaining ungoverned personal data.
    op.execute(
        "UPDATE whatsapp_webhook_events SET payload = NULL, status = 'PROCESSED', "
        "processed_at = COALESCE(processed_at, now())"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_whatsapp_webhook_events_organization_id",
        table_name="whatsapp_webhook_events",
    )
    op.drop_constraint(
        "fk_whatsapp_webhook_events_organization_id_organizations",
        "whatsapp_webhook_events",
        type_="foreignkey",
    )
    op.drop_column("whatsapp_webhook_events", "organization_id")
