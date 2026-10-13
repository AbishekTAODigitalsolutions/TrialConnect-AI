"""add conversation message read status

Revision ID: 20261012_message_read_status
Revises: 20261011_remove_patient_invites
Create Date: 2026-10-12 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.config import settings

revision = "20261012_message_read_status"
down_revision = "20261011_remove_patient_invites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        schema=settings.POSTGRES_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("conversation_messages", "read_at", schema=settings.POSTGRES_SCHEMA)
