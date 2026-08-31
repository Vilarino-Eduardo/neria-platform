"""add automatic assignment

Revision ID: f18c572d3406
Revises: e07b461c2395
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f18c572d3406"
down_revision: str | None = "e07b461c2395"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization_profiles",
        sa.Column("auto_assignment_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("organization_profiles", "auto_assignment_enabled", server_default=None)
    op.add_column(
        "users",
        sa.Column("accepts_assignments", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.alter_column("users", "accepts_assignments", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "accepts_assignments")
    op.drop_column("organization_profiles", "auto_assignment_enabled")
