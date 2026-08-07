from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.media_access import MediaAccessService
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake


@pytest.mark.asyncio
async def test_signed_url_is_not_created_for_other_organization() -> None:
    with pytest.raises(DomainError, match="不存在或無法存取"):
        await MediaAccessService(InMemoryStorageFake(), uuid4()).signed_url(
            media_organization_id=uuid4(), object_key="photo"
        )
