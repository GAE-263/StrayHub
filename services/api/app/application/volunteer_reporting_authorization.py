from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.identity import OrganizationMembership
from services.api.app.persistence.models.volunteer_access import VolunteerAccessGrant
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)


@dataclass(frozen=True)
class VolunteerReportingAuthorization:
    membership: OrganizationMembership
    grant: VolunteerAccessGrant
    animal: Animal | None = None


class VolunteerReportingAuthorizationService:
    """Authorize ordinary reporting without interpreting legacy daily scopes."""

    def __init__(
        self,
        authentication: AuthenticationRepository,
        animals: AnimalRepository,
    ) -> None:
        self.authentication = authentication
        self.animals = animals

    async def authorize(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        membership_id: UUID | None = None,
        animal_id: UUID | None = None,
        animal_unavailable_status: int = 404,
    ) -> VolunteerReportingAuthorization:
        user = await self.authentication.get_user(user_id)
        organization = await self.authentication.get_organization(organization_id)
        if (
            user is None
            or user.status != "active"
            or organization is None
            or organization.status != "active"
        ):
            raise self._authorization_error()

        access = await self.authentication.lock_effective_volunteer_access(user_id, organization_id)
        if access is None:
            raise self._authorization_error()
        membership, grant = access
        if (
            (membership_id is not None and membership.id != membership_id)
            or membership.user_id != user_id
            or membership.organization_id != organization_id
            or membership.role != "VOLUNTEER"
            or membership.status != "active"
            or grant.user_id != user_id
            or grant.organization_id != organization_id
            or grant.membership_id != membership.id
            or grant.status != "active"
        ):
            raise self._authorization_error()

        animal = None
        if animal_id is not None:
            animal = await self.animals.get(animal_id)
            if (
                animal is None
                or animal.organization_id != organization_id
                or animal.status != "active"
            ):
                raise DomainError(
                    "animal_no_longer_available",
                    "動物目前無法進行照護回報",
                    animal_unavailable_status,
                )
        return VolunteerReportingAuthorization(
            membership=membership,
            grant=grant,
            animal=animal,
        )

    @staticmethod
    def _authorization_error() -> DomainError:
        return DomainError(
            "authorization_no_longer_valid",
            "目前無法開始此照護回報",
            403,
        )
