"""add conversation priority

Revision ID: c85f249a0173
Revises: b74e1c6f9302
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c85f249a0173"
down_revision: str | None = "b74e1c6f9302"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("priority", sa.String(length=20), server_default="NORMAL", nullable=False),
    )
    op.alter_column("conversations", "priority", server_default=None)


def downgrade() -> None:
    op.drop_column("conversations", "priority")
