"""rename participants to patients and add patient accounts

Revision ID: 20261007_patient_accounts
Revises: 20241007_create_participants
Create Date: 2026-10-07 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.config import settings

revision = "20261007_patient_accounts"
down_revision = "20241007_create_participants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.POSTGRES_SCHEMA
    op.rename_table("participants", "patients", schema=schema)
    op.create_table(
        "patient_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            [f"{schema}.patients.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("patient_id"),
        sa.UniqueConstraint("email"),
        schema=schema,
    )
    op.create_table(
        "patient_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            [f"{schema}.patients.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
        schema=schema,
    )
    op.create_index(
        "ix_patient_invites_patient_id",
        "patient_invites",
        ["patient_id"],
        schema=schema,
    )


def downgrade() -> None:
    schema = settings.POSTGRES_SCHEMA
    op.drop_index("ix_patient_invites_patient_id", table_name="patient_invites", schema=schema)
    op.drop_table("patient_invites", schema=schema)
    op.drop_table("patient_accounts", schema=schema)
    op.rename_table("patients", "participants", schema=schema)
