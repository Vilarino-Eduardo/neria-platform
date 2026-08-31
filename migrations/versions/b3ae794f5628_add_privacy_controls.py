"""add privacy controls

Revision ID: b3ae794f5628
Revises: a29d683e4517
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3ae794f5628"
down_revision: str | None = "a29d683e4517"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization_profiles",
        sa.Column("data_retention_days", sa.Integer(), server_default="365", nullable=False),
    )
    op.alter_column("organization_profiles", "data_retention_days", server_default=None)
    op.add_column(
        "contacts",
        sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contacts", "anonymized_at")
    op.drop_column("organization_profiles", "data_retention_days")
