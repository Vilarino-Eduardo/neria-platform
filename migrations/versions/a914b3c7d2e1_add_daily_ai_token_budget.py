"""add daily ai token budget

Revision ID: a914b3c7d2e1
Revises: e6b91c3d205f
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a914b3c7d2e1"
down_revision: str | None = "e6b91c3d205f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "ai_daily_token_limit",
            sa.Integer(),
            server_default="100000",
            nullable=False,
        ),
    )
    op.alter_column("subscriptions", "ai_daily_token_limit", server_default=None)
    op.add_column(
        "ai_usage_daily",
        sa.Column(
            "reserved_tokens",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.alter_column("ai_usage_daily", "reserved_tokens", server_default=None)


def downgrade() -> None:
    op.drop_column("ai_usage_daily", "reserved_tokens")
    op.drop_column("subscriptions", "ai_daily_token_limit")
