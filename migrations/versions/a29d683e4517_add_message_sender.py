"""add message sender

Revision ID: a29d683e4517
Revises: f18c572d3406
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a29d683e4517"
down_revision: str | None = "f18c572d3406"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("sender_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_messages_sender_user_id_users"),
        "messages",
        "users",
        ["sender_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_messages_sender_user_id"), "messages", ["sender_user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_messages_sender_user_id"), table_name="messages")
    op.drop_constraint(op.f("fk_messages_sender_user_id_users"), "messages", type_="foreignkey")
    op.drop_column("messages", "sender_user_id")
