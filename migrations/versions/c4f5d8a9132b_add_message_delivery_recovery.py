"""add message delivery recovery

Revision ID: c4f5d8a9132b
Revises: b3ae794f5628
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4f5d8a9132b"
down_revision: str | None = "b3ae794f5628"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("delivery_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.alter_column("messages", "delivery_attempts", server_default=None)
    op.add_column("messages", sa.Column("delivery_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "delivery_error")
    op.drop_column("messages", "delivery_attempts")
