"""Pure value objects for selecting one volunteer workflow target."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from services.api.app.api.errors import DomainError

_ENTRY_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9._~-]+$")


@dataclass(frozen=True, slots=True)
class OrganizationTarget:
    organization_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.organization_id, UUID):
            raise DomainError("invalid_target", "organization_id 格式無效", 422)


@dataclass(frozen=True, slots=True)
class EntryTarget:
    shelter_entry_reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.shelter_entry_reference, str):
            raise DomainError("invalid_target", "shelter_entry_reference 格式無效", 422)
        reference = self.shelter_entry_reference
        if reference != reference.strip():
            raise DomainError("invalid_target", "shelter_entry_reference 格式無效", 422)
        if not 32 <= len(reference) <= 512 or not _ENTRY_REFERENCE_PATTERN.fullmatch(reference):
            raise DomainError("invalid_target", "shelter_entry_reference 格式無效", 422)

    def __repr__(self) -> str:
        return "EntryTarget(shelter_entry_reference='<redacted>')"

    __str__ = __repr__


VolunteerTarget = OrganizationTarget | EntryTarget


def build_volunteer_target(
    *,
    organization_id: UUID | None = None,
    shelter_entry_reference: str | None = None,
) -> VolunteerTarget:
    if organization_id is None:
        if shelter_entry_reference is None:
            raise DomainError(
                "target_required",
                "必須指定 organization_id 或 shelter_entry_reference",
                422,
            )
        return EntryTarget(shelter_entry_reference=shelter_entry_reference)
    if shelter_entry_reference is not None:
        raise DomainError(
            "target_ambiguous",
            "organization_id 與 shelter_entry_reference 不可同時指定",
            422,
        )
    return OrganizationTarget(organization_id=organization_id)
