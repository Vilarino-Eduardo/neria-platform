"""add quick replies

Revision ID: a63d814c9f25
Revises: f19a52e7b840
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a63d814c9f25"
down_revision: str | Sequence[str] | None = "f19a52e7b840"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quick_replies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("shortcut", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_quick_replies_organization_id_organizations"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quick_replies")),
        sa.UniqueConstraint("organization_id", "shortcut", name=op.f("uq_quick_replies_organization_id")),
    )
    op.create_index(op.f("ix_quick_replies_organization_id"), "quick_replies", ["organization_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_quick_replies_organization_id"), table_name="quick_replies")
    op.drop_table("quick_replies")
