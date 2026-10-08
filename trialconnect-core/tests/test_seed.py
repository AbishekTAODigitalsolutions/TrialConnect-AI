import asyncio

from app.database.seed import seed_patients


def test_seed_patients() -> None:
    result = asyncio.run(seed_patients())
    assert result["total"] >= 20
