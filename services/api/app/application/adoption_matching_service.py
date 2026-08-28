from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.domain.adoption_matching import (
    AdopterPreferences,
    AnimalProfile,
    MatchScore,
    rank_animals,
    score_single,
)
from services.api.app.persistence.models.animal import Animal


def _to_profile(animal: Animal) -> AnimalProfile:
    return AnimalProfile(
        animal_id=animal.id,
        size=animal.size,
        energy=animal.energy,
        temperament=tuple(animal.temperament or ()),
        is_adoptable=animal.is_adoptable,
    )


class AdoptionMatchingService:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def recommend(
        self, preferences: AdopterPreferences, *, top_n: int = 3
    ) -> list[MatchScore]:
        rows = await self.session.execute(
            select(Animal).where(
                Animal.organization_id == self.organization_id,
                Animal.is_adoptable.is_(True),
                Animal.status == "active",
            )
        )
        candidates = [_to_profile(animal) for animal in rows.scalars()]
        return rank_animals(preferences, candidates, top_n=top_n)

    async def score_target(
        self, animal_id: UUID, preferences: AdopterPreferences
    ) -> MatchScore | None:
        """Score the one already-chosen animal for the 心有所屬 path.

        Returns None if the animal can no longer be found in this
        organization — callers decide how to handle a vanished target."""
        rows = await self.session.execute(
            select(Animal).where(
                Animal.id == animal_id,
                Animal.organization_id == self.organization_id,
            )
        )
        animal = rows.scalar_one_or_none()
        if animal is None:
            return None
        return score_single(preferences, _to_profile(animal))
