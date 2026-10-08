from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.participant import Patient


FIRST_NAMES = [
    "Ava", "Noah", "Mila", "Leo", "Zoe", "Ethan", "Ivy", "Mason", "Luna", "Owen",
    "Harper", "Lucas", "Clara", "Daniel", "Emma", "Henry", "Chloe", "Jack", "Grace", "Nora",
]
LAST_NAMES = [
    "Adams", "Bennett", "Carter", "Davis", "Evans", "Foster", "Garcia", "Hughes", "Ingram", "Jenkins",
    "King", "Lopez", "Moore", "Nolan", "Owens", "Parker", "Quinn", "Rivera", "Stone", "Turner",
]


async def seed_patients() -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        current = await session.scalar(select(func.count()).select_from(Patient))
        if current >= 20:
            total_count = await session.scalar(select(func.count()).select_from(Patient))
            return {"seeded": 0, "total": total_count}

        patients = []
        for index in range(20):
            first_name = FIRST_NAMES[index % len(FIRST_NAMES)]
            last_name = LAST_NAMES[index % len(LAST_NAMES)]
            patient = Patient(
                id=uuid4(),
                external_id=f"TP-{1000 + index}",
                given_name=first_name,
                family_name=last_name,
                email=f"participant{index + 1}@synthetic.example",
                study_id="STUDY-001",
                site_id=f"SITE-{(index % 5) + 1:02d}",
                timezone="UTC",
                is_active=True,
            )
            patients.append(patient)
        session.add_all(patients)
        await session.commit()

        total_count = await session.scalar(select(func.count()).select_from(Patient))
        return {"seeded": len(patients), "total": total_count}


seed_participants = seed_patients


async def main() -> None:
    result = await seed_patients()
    print(f"Seeded synthetic patients: {result['seeded']} | total: {result['total']}")


if __name__ == "__main__":
    asyncio.run(main())
