"""add conversation unread count

Revision ID: f19a52e7b840
Revises: e58c40a6149b
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f19a52e7b840"
down_revision: str | Sequence[str] | None = "e58c40a6149b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("unread_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.alter_column("conversations", "unread_count", server_default=None)


def downgrade() -> None:
    op.drop_column("conversations", "unread_count")
