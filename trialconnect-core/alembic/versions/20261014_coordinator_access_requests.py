"""add admin-approved coordinator access requests

Revision ID: 20261014_coord_access
Revises: 20261013_coordinator_rbac
Create Date: 2026-10-14 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.config import settings

revision = "20261014_coord_access"
down_revision = "20261013_coordinator_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = settings.POSTGRES_SCHEMA
    op.create_table(
        "coordinator_access_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("notification_status", sa.String(length=24), nullable=False),
        sa.Column("notification_error", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            [f"{schema}.coordinator_accounts.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        schema=schema,
    )
    op.create_index(
        "ix_coordinator_access_requests_status_created",
        "coordinator_access_requests",
        ["status", "created_at"],
        schema=schema,
    )


def downgrade() -> None:
    schema = settings.POSTGRES_SCHEMA
    op.drop_index(
        "ix_coordinator_access_requests_status_created",
        table_name="coordinator_access_requests",
        schema=schema,
    )
    op.drop_table("coordinator_access_requests", schema=schema)
