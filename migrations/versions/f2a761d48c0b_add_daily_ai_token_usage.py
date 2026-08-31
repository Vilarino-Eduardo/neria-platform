"""add daily ai token usage

Revision ID: f2a761d48c0b
Revises: ad8e24c91f70
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a761d48c0b"
down_revision: str | None = "ad8e24c91f70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_usage_daily",
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "ai_usage_daily",
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
    )
    op.alter_column("ai_usage_daily", "input_tokens", server_default=None)
    op.alter_column("ai_usage_daily", "output_tokens", server_default=None)


def downgrade() -> None:
    op.drop_column("ai_usage_daily", "output_tokens")
    op.drop_column("ai_usage_daily", "input_tokens")
