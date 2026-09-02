"""add message idempotency

Revision ID: d3d8c9472f1a
Revises: b4fd768122c1
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3d8c9472f1a"
down_revision: str | None = "b4fd768122c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("idempotency_key", sa.String(length=128)))
    op.add_column("messages", sa.Column("idempotency_payload_hash", sa.String(length=64)))
    op.create_unique_constraint(
        "uq_messages_organization_idempotency_key",
        "messages",
        ["organization_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_messages_organization_idempotency_key",
        "messages",
        type_="unique",
    )
    op.drop_column("messages", "idempotency_payload_hash")
    op.drop_column("messages", "idempotency_key")
