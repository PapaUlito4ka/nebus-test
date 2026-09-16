"""create payments table

Revision ID: 0001
Revises:
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    currency_enum = postgresql.ENUM("RUB", "USD", "EUR", name="currency")
    status_enum = postgresql.ENUM("pending", "succeeded", "failed", name="payment_status")

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", currency_enum, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", status_enum, nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(), nullable=False, unique=True),
        sa.Column("webhook_url", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
    )


def downgrade() -> None:
    op.drop_table("payments")
    postgresql.ENUM(name="payment_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="currency").drop(op.get_bind(), checkfirst=True)
