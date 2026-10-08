"""add appointments and in-app reminder notifications

Revision ID: 20261009_appointment_reminders
Revises: 20261008_conversations
Create Date: 2026-10-09 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.config import settings

revision = "20261009_appointment_reminders"
down_revision = "20261008_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.POSTGRES_SCHEMA
    op.create_table(
        "appointments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            [f"{schema}.patients.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index(
        "ix_appointments_patient_scheduled",
        "appointments",
        ["patient_id", "starts_at"],
        schema=schema,
    )
    op.create_table(
        "patient_notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("reminder_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("appointment_id", "reminder_type", name="uq_notification_appointment_reminder"),
        schema=schema,
    )
    op.create_index(
        "ix_patient_notifications_patient_created",
        "patient_notifications",
        ["patient_id", "created_at"],
        schema=schema,
    )


def downgrade() -> None:
    schema = settings.POSTGRES_SCHEMA
    op.drop_index("ix_patient_notifications_patient_created", table_name="patient_notifications", schema=schema)
    op.drop_table("patient_notifications", schema=schema)
    op.drop_index("ix_appointments_patient_scheduled", table_name="appointments", schema=schema)
    op.drop_table("appointments", schema=schema)
