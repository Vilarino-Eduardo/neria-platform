"""add knowledge processing claim

Revision ID: 9d5e2f38a7b4
Revises: 8c4d1e27f6a3
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d5e2f38a7b4"
down_revision: str | Sequence[str] | None = "8c4d1e27f6a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_sources",
        sa.Column("processing_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column("processing_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("knowledge_sources", "processing_attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("knowledge_sources", "processing_claimed_at")
    op.drop_column("knowledge_sources", "processing_attempts")
