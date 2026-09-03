"""Seed the frozen, non-diagnostic six-question walk vocabulary."""

from __future__ import annotations

from collections.abc import Iterable

CATEGORY_NAMES = {
    "walk_completion": "散步完成",
    "activity": "活動狀況",
    "gait": "走路狀況",
    "defecation": "排便狀況",
    "animal_interaction": "遇到其他動物時",
    "appearance_special_status": "外觀／特殊狀態",
}

OPTION_NAMES = {
    "walk_completion.completed": "有走完",
    "walk_completion.partially_completed": "走一半",
    "walk_completion.not_done": "沒走成",
    "activity.higher": "比平常好",
    "activity.usual": "跟平常一樣",
    "activity.lower": "比平常差",
    "gait.normal": "正常",
    "gait.off": "有點怪",
    "gait.abnormal": "明顯不對",
    "defecation.normal": "正常",
    "defecation.soft": "偏軟",
    "defecation.none": "沒排便",
    "defecation.abnormal": "有異狀",
    "animal_interaction.friendly": "友善",
    "animal_interaction.no_reaction": "沒反應",
    "animal_interaction.wary": "緊張或想衝",
    "animal_interaction.no_encounter": "路上沒遇到",
    "appearance.none_found": "沒發現異狀",
    "appearance.skin_or_coat": "皮膚或毛髮異常",
    "appearance.wound": "傷口或紅腫",
    "appearance.other": "其他",
}

PLATFORM_OPTIONS: dict[str, tuple[str, ...]] = {
    "walk_completion": (
        "walk_completion.completed",
        "walk_completion.partially_completed",
        "walk_completion.not_done",
    ),
    "activity": ("activity.higher", "activity.usual", "activity.lower"),
    "gait": ("gait.normal", "gait.off", "gait.abnormal"),
    "defecation": (
        "defecation.normal",
        "defecation.soft",
        "defecation.none",
        "defecation.abnormal",
    ),
    "animal_interaction": (
        "animal_interaction.friendly",
        "animal_interaction.no_reaction",
        "animal_interaction.wary",
        "animal_interaction.no_encounter",
    ),
    "appearance_special_status": (
        "appearance.none_found",
        "appearance.skin_or_coat",
        "appearance.wound",
        "appearance.other",
    ),
}


def iter_platform_options() -> Iterable[tuple[str, str]]:
    for category, codes in PLATFORM_OPTIONS.items():
        for code in codes:
            yield category, code


async def seed_vocabulary(session) -> None:
    """Upsert current defaults and disable superseded platform options."""
    from services.api.app.persistence.models.observation import (
        ObservationCategory,
        ObservationOption,
    )
    from sqlalchemy import select

    active_codes = {code for codes in PLATFORM_OPTIONS.values() for code in codes}
    old_options = await session.scalars(
        select(ObservationOption).where(ObservationOption.organization_id.is_(None))
    )
    for option in old_options:
        if option.code not in active_codes:
            option.status = "disabled"

    for category_code, codes in PLATFORM_OPTIONS.items():
        category = await session.scalar(
            select(ObservationCategory).where(
                ObservationCategory.organization_id.is_(None),
                ObservationCategory.code == category_code,
            )
        )
        if category is None:
            category = ObservationCategory(
                organization_id=None,
                code=category_code,
                display_name=CATEGORY_NAMES[category_code],
                description="非診斷性散步觀察語彙",
                status="active",
            )
            session.add(category)
            await session.flush()
        category.display_name = CATEGORY_NAMES[category_code]
        category.status = "active"
        for code in codes:
            option = await session.scalar(
                select(ObservationOption).where(
                    ObservationOption.category_id == category.id,
                    ObservationOption.code == code,
                )
            )
            if option is None:
                option = ObservationOption(
                    category_id=category.id,
                    organization_id=None,
                    code=code,
                    display_name=OPTION_NAMES[code],
                )
                session.add(option)
            option.display_name = OPTION_NAMES[code]
            option.description = "非診斷性散步觀察選項"
            option.status = "active"
            option.requires_note = code in {
                "gait.abnormal",
                "defecation.abnormal",
                "appearance.skin_or_coat",
                "appearance.wound",
                "appearance.other",
            }
        await session.flush()


def main() -> None:
    for category, code in iter_platform_options():
        print(f"{category}\t{code}")


if __name__ == "__main__":
    main()
