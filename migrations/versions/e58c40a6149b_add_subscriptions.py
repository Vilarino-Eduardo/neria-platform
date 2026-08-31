"""add subscriptions

Revision ID: e58c40a6149b
Revises: d41b7392a603
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e58c40a6149b"
down_revision: str | Sequence[str] | None = "d41b7392a603"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_code", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_customer_id", sa.String(length=160), nullable=True),
        sa.Column("external_subscription_id", sa.String(length=160), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name=op.f("fk_subscriptions_organization_id_organizations"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
        sa.UniqueConstraint("organization_id", name=op.f("uq_subscriptions_organization_id")),
    )
    op.execute(
        """
        INSERT INTO subscriptions (id, organization_id, plan_code, status)
        SELECT gen_random_uuid(), id, 'starter', 'ACTIVE' FROM organizations
        """
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
