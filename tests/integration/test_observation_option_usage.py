from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.observation_option_usage_service import (
    ObservationOptionUsageService,
)


def test_usage_snapshot_keeps_original_text_and_resolves_fixed_category_code() -> None:
    option_id = uuid4()
    category_id = uuid4()
    option = SimpleNamespace(
        id=option_id,
        category_id=category_id,
        code="appearance.changed",
        display_name="目前名稱",
        description="目前說明",
    )
    service = object.__new__(ObservationOptionUsageService)

    category, display_name, description, resolved_id = service._snapshot_value(
        "appearance_special_status",
        "appearance.changed",
        {
            "appearance_special_status": {
                "category_code": "appearance_special_status",
                "code": "appearance.changed",
                "display_name": "歷史名稱",
                "description": "歷史說明",
            }
        },
        {"appearance.changed": option},
        {category_id: "appearance_special_status"},
    )

    assert category == "appearance_special_status"
    assert display_name == "歷史名稱"
    assert description == "歷史說明"
    assert resolved_id == option_id


@pytest.mark.asyncio
async def test_usage_index_rejects_a_report_from_another_shelter() -> None:
    service = object.__new__(ObservationOptionUsageService)
    service.organization_id = uuid4()
    report = SimpleNamespace(organization_id=uuid4())

    with pytest.raises(ValueError, match="scope mismatch"):
        await service.index_report(report)
