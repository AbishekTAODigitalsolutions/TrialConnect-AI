"""add appointment email delivery outbox

Revision ID: 20261010_appointment_email
Revises: 20261009_appointment_reminders
Create Date: 2026-10-10 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.config import settings

revision = "20261010_appointment_email"
down_revision = "20261009_appointment_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.POSTGRES_SCHEMA
    op.create_table(
        "appointment_email_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("email_type", sa.String(length=32), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            [f"{schema}.patients.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"],
            [f"{schema}.appointments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("appointment_id", "email_type", name="uq_appointment_email_type"),
        schema=schema,
    )
    op.create_index(
        "ix_appointment_email_deliveries_due",
        "appointment_email_deliveries",
        ["status", "next_attempt_at", "scheduled_for"],
        schema=schema,
    )


def downgrade() -> None:
    schema = settings.POSTGRES_SCHEMA
    op.drop_index(
        "ix_appointment_email_deliveries_due",
        table_name="appointment_email_deliveries",
        schema=schema,
    )
    op.drop_table("appointment_email_deliveries", schema=schema)
