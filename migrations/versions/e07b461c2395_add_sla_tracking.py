"""add sla tracking

Revision ID: e07b461c2395
Revises: d96a350b1284
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e07b461c2395"
down_revision: str | None = "d96a350b1284"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization_profiles",
        sa.Column("sla_first_response_minutes", sa.Integer(), server_default="15", nullable=False),
    )
    op.alter_column("organization_profiles", "sla_first_response_minutes", server_default=None)
    op.add_column(
        "conversations",
        sa.Column("last_human_response_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "last_human_response_at")
    op.drop_column("organization_profiles", "sla_first_response_minutes")
