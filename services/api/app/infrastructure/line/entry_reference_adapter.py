"""Resolve opaque volunteer entry references through the existing CRM resolver."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.application.ports.authentication import ActiveVolunteerEntryReference
from services.api.app.domain.volunteer_access import (
    ENTRY_REFERENCE_PURPOSE,
    digest_entry_reference,
)
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)


class VolunteerEntryReferenceAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(self, raw_reference: str) -> ActiveVolunteerEntryReference | None:
        normalized = raw_reference.strip()
        if not normalized:
            return None
        resolved = await VolunteerAccessRepository.resolve_entry_reference(
            self.session,
            token_digest=digest_entry_reference(normalized),
            purpose=ENTRY_REFERENCE_PURPOSE,
        )
        if resolved is None:
            return None
        reference_id, organization_id, organization_code, organization_name = resolved
        return ActiveVolunteerEntryReference(
            reference_id=reference_id,
            organization_id=organization_id,
            organization_code=organization_code,
            organization_name=organization_name,
        )
