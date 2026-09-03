"""add ai processing claim

Revision ID: c61a82f4d207
Revises: a914b3c7d2e1
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c61a82f4d207"
down_revision: str | None = "a914b3c7d2e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_runs",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ai_runs",
        sa.Column(
            "token_reservation",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.alter_column("ai_runs", "token_reservation", server_default=None)


def downgrade() -> None:
    op.drop_column("ai_runs", "token_reservation")
    op.drop_column("ai_runs", "processing_started_at")
