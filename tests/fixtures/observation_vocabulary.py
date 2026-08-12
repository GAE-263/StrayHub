"""Deterministic fixtures for observation vocabulary management tests."""

from __future__ import annotations

from uuid import UUID, uuid4

from scripts.seed_observation_vocabulary import PLATFORM_OPTIONS

OBSERVATION_CATEGORY_NAMES = {
    "care_completion": "照護完成",
    "walk_completion": "散步完成",
    "feeding": "進食",
    "water": "飲水",
    "activity": "活動",
    "urination": "排尿",
    "defecation": "排便",
    "resource_guarding": "護食",
    "human_interaction": "人際互動",
    "animal_interaction": "動物互動",
    "emotion": "情緒",
    "walk": "散步",
    "appearance_special_status": "外觀／特殊狀態",
}


def observation_vocabulary_fixture(
    organization_id: UUID | None = None,
) -> dict[str, object]:
    """Return two-tenant-shaped data without touching a database."""

    organization_id = organization_id or uuid4()
    categories = [
        {
            "id": uuid4(),
            "code": code,
            "display_name": OBSERVATION_CATEGORY_NAMES[code],
        }
        for code in PLATFORM_OPTIONS
    ]
    return {
        "organization_id": organization_id,
        "categories": categories,
        "platform_codes": [code for codes in PLATFORM_OPTIONS.values() for code in codes],
        "custom_options": [
            {
                "id": uuid4(),
                "code": "emotion.shelter_calm",
                "display_name": "收容所自訂平靜",
                "status": "active",
                "organization_id": organization_id,
            },
            {
                "id": uuid4(),
                "code": "emotion.historical_old",
                "display_name": "歷史舊詞彙",
                "status": "disabled",
                "organization_id": organization_id,
                "has_historical_usage": True,
            },
        ],
    }
