"""add password reset delivery

Revision ID: 8c4d1e27f6a3
Revises: 7a3c9d10e5f2
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c4d1e27f6a3"
down_revision: str | Sequence[str] | None = "7a3c9d10e5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("password_reset_tokens", sa.Column("delivery_token_encrypted", sa.Text()))
    op.add_column(
        "password_reset_tokens",
        sa.Column("delivery_status", sa.String(length=20), server_default="SENT", nullable=False),
    )
    op.add_column(
        "password_reset_tokens",
        sa.Column("delivery_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("password_reset_tokens", sa.Column("delivery_error", sa.Text()))
    op.add_column(
        "password_reset_tokens", sa.Column("delivery_claimed_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "password_reset_tokens", sa.Column("delivered_at", sa.DateTime(timezone=True))
    )
    op.alter_column("password_reset_tokens", "delivery_status", server_default=None)
    op.alter_column("password_reset_tokens", "delivery_attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("password_reset_tokens", "delivered_at")
    op.drop_column("password_reset_tokens", "delivery_claimed_at")
    op.drop_column("password_reset_tokens", "delivery_error")
    op.drop_column("password_reset_tokens", "delivery_attempts")
    op.drop_column("password_reset_tokens", "delivery_status")
    op.drop_column("password_reset_tokens", "delivery_token_encrypted")
