from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models.base import Base
from app.models import appointment as appointment_models
from app.models import conversation as conversation_models
from app.models import coordinator_account as coordinator_models
from app.models import patient_account as patient_account_models
from app.models import participant as patient_models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        version_table_schema=settings.POSTGRES_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        async with connection.begin():
            await connection.execute(
                text(f'CREATE SCHEMA IF NOT EXISTS "{settings.POSTGRES_SCHEMA}"')
            )
            await connection.execute(
                text(f'SET search_path TO "{settings.POSTGRES_SCHEMA}"')
            )
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
