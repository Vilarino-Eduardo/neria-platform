"""add message delivery claim

Revision ID: e6b91c3d205f
Revises: d3d8c9472f1a
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6b91c3d205f"
down_revision: str | None = "d3d8c9472f1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("delivery_claimed_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("messages", "delivery_claimed_at")
