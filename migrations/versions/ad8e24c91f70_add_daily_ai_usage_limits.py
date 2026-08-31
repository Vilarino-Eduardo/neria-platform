"""add daily ai usage limits

Revision ID: ad8e24c91f70
Revises: c4f5d8a9132b
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ad8e24c91f70"
down_revision: str | None = "c4f5d8a9132b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "ai_daily_request_limit",
            sa.Integer(),
            server_default="50",
            nullable=False,
        ),
    )
    op.alter_column("subscriptions", "ai_daily_request_limit", server_default=None)
    op.create_table(
        "ai_usage_daily",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("request_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_ai_usage_daily_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "usage_date", name=op.f("pk_ai_usage_daily")
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_usage_daily")
    op.drop_column("subscriptions", "ai_daily_request_limit")
