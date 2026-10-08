"""add patient-coordinator conversation messages

Revision ID: 20261008_conversations
Revises: 20261007_patient_accounts
Create Date: 2026-10-08 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.config import settings

revision = "20261008_conversations"
down_revision = "20261007_patient_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.POSTGRES_SCHEMA
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("sender", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
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
        "ix_conversation_messages_patient_created",
        "conversation_messages",
        ["patient_id", "created_at"],
        schema=schema,
    )


def downgrade() -> None:
    schema = settings.POSTGRES_SCHEMA
    op.drop_index("ix_conversation_messages_patient_created", table_name="conversation_messages", schema=schema)
    op.drop_table("conversation_messages", schema=schema)
