import redis.asyncio as redis

from app.config import settings


async def get_redis_client() -> redis.Redis:
    client = redis.from_url(settings.redis_url, decode_responses=True)
    return client


async def check_redis() -> tuple[bool, str]:
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.ping()
        return True, "redis_ok"
    except Exception as exc:  # pragma: no cover - defensive path
        return False, str(exc)
    finally:
        await client.aclose()
