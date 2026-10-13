"""add coordinator accounts, audit events, and read receipts

Revision ID: 20261013_coordinator_rbac
Revises: 20261012_message_read_status
Create Date: 2026-10-13 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.config import settings

revision = "20261013_coordinator_rbac"
down_revision = "20261012_message_read_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.POSTGRES_SCHEMA
    op.create_table(
        "coordinator_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        schema=schema,
    )
    op.create_index(
        "ix_coordinator_accounts_role_active",
        "coordinator_accounts",
        ["role", "is_active"],
        schema=schema,
    )
    op.create_table(
        "coordinator_message_reads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("coordinator_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["coordinator_id"],
            [f"{schema}.coordinator_accounts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            [f"{schema}.conversation_messages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id",
            "coordinator_id",
            name="uq_coordinator_message_read",
        ),
        schema=schema,
    )
    op.create_index(
        "ix_coordinator_message_reads_coordinator_read",
        "coordinator_message_reads",
        ["coordinator_id", "read_at"],
        schema=schema,
    )
    op.create_table(
        "coordinator_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("coordinator_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("patient_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["coordinator_id"],
            [f"{schema}.coordinator_accounts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            [f"{schema}.conversation_messages.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            [f"{schema}.patients.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index(
        "ix_coordinator_audit_events_created",
        "coordinator_audit_events",
        ["created_at"],
        schema=schema,
    )


def downgrade() -> None:
    schema = settings.POSTGRES_SCHEMA
    op.drop_index("ix_coordinator_audit_events_created", table_name="coordinator_audit_events", schema=schema)
    op.drop_table("coordinator_audit_events", schema=schema)
    op.drop_index(
        "ix_coordinator_message_reads_coordinator_read",
        table_name="coordinator_message_reads",
        schema=schema,
    )
    op.drop_table("coordinator_message_reads", schema=schema)
    op.drop_index("ix_coordinator_accounts_role_active", table_name="coordinator_accounts", schema=schema)
    op.drop_table("coordinator_accounts", schema=schema)
