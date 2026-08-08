from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.api.app.infrastructure.storage.ports import ObjectScope
from services.worker.app.handlers.ai_handler import AIJobHandler
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter


@pytest.mark.asyncio
async def test_full_cross_tenant_matrix_keeps_database_media_and_ai_scoped() -> None:
    from tests.isolation.test_cross_tenant_resource_matrix import (
        test_a_b_resource_matrix_hides_business_resources_and_signed_media,
    )

    await test_a_b_resource_matrix_hides_business_resources_and_signed_media()

    organization_a, organization_b = uuid4(), uuid4()
    storage = InMemoryStorageFake()
    metadata = storage.metadata_for(b"clean", content_type="image/jpeg", checksum="a" * 64)
    await storage.put(
        scope=ObjectScope(organization_b), key="reports/photo.jpg", data=b"clean", metadata=metadata
    )
    with pytest.raises(DomainError, match="不存在或無法存取"):
        await storage.get(scope=ObjectScope(organization_a), key="reports/photo.jpg")

    adapter = MockAIAdapter()
    job = SimpleNamespace(
        organization_id=organization_b,
        target_type="care_report",
        target_id=uuid4(),
        status="pending",
        provider="mock",
        model_name="local",
        model_version="v1",
        prompt_template_id="care",
        prompt_version="v1",
        output_schema_version="v1",
    )
    with pytest.raises(DomainError, match="目前收容所不一致"):
        await AIJobHandler(adapter).handle(
            job,
            note=None,
            cleaned_images=[],
            allowed_codes=set(),
            organization_id=organization_a,
        )
    assert adapter.requests == []
