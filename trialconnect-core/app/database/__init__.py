"""Database helpers and seed utilities."""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_database() -> tuple[bool, str]:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True, "database_ok"
    except Exception as exc:  # pragma: no cover - defensive path
        return False, str(exc)


async def check_vector_extension() -> tuple[bool, str]:
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"))
            exists = result.scalar_one()
        return exists, "vector_enabled" if exists else "vector_missing"
    except Exception as exc:  # pragma: no cover - defensive path
        return False, str(exc)
