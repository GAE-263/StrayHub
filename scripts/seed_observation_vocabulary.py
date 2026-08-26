"""Seed the platform's non-diagnostic Observation Vocabulary."""

from __future__ import annotations

from collections.abc import Iterable

CATEGORY_NAMES = {
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

OPTION_NAMES = {
    "completed": "已完成",
    "partially_completed": "部分完成",
    "not_provided": "未提供",
    "not_observed": "未觀察到",
    "uncertain": "不確定",
    "not_done": "未完成",
    "normal": "正常",
    "less": "較少",
    "almost_none": "幾乎沒有",
    "observed": "有觀察到",
    "usual": "平常",
    "lower": "較低",
    "higher": "較高",
    "unwilling": "不願意",
    "formed": "成形",
    "soft": "偏軟",
    "watery": "水樣",
    "different_color": "顏色不同",
    "different_shape": "形狀不同",
    "tense": "緊繃",
    "vocalizes": "發出聲音",
    "blocks": "阻擋",
    "moves_food": "移動食物",
    "no_approach": "不靠近",
    "seeking": "主動尋求",
    "avoidant": "迴避",
    "calm": "平靜",
    "alert": "警覺",
    "excited": "興奮",
    "withdrawn": "退縮",
    "seeking_interaction": "尋求互動",
    "willing": "願意",
    "exploring": "探索",
    "reluctant": "猶豫",
    "slow_or_stopping": "變慢或停下",
    "tries_to_return": "嘗試返回",
    "human_reaction": "對人的反應",
    "animal_reaction": "對動物的反應",
    "changed": "外觀改變",
    "scratching": "搔抓",
    "red_area": "泛紅區域",
    "reduced_hair": "毛髮變少",
    "lying_long": "長時間躺臥",
    "different_walk": "行走不同",
    "other": "其他",
}

PLATFORM_OPTIONS: dict[str, tuple[str, ...]] = {
    "care_completion": (
        "care_completion.completed",
        "care_completion.partially_completed",
        "care_completion.not_provided",
        "care_completion.not_observed",
        "care_completion.uncertain",
    ),
    "walk_completion": (
        "walk_completion.completed",
        "walk_completion.partially_completed",
        "walk_completion.not_done",
        "walk_completion.not_observed",
        "walk_completion.uncertain",
    ),
    "feeding": (
        "feeding.normal",
        "feeding.less",
        "feeding.almost_none",
        "feeding.not_provided",
        "feeding.not_observed",
        "feeding.uncertain",
    ),
    "water": (
        "water.observed",
        "water.less",
        "water.not_observed",
        "water.not_provided",
        "water.uncertain",
    ),
    "activity": (
        "activity.usual",
        "activity.lower",
        "activity.higher",
        "activity.unwilling",
        "activity.not_observed",
        "activity.uncertain",
    ),
    "urination": ("urination.observed", "urination.not_observed", "urination.uncertain"),
    "defecation": (
        "defecation.formed",
        "defecation.soft",
        "defecation.watery",
        "defecation.different_color",
        "defecation.different_shape",
        "defecation.not_observed",
        "defecation.uncertain",
    ),
    "resource_guarding": (
        "resource_guarding.not_observed",
        "resource_guarding.tense",
        "resource_guarding.vocalizes",
        "resource_guarding.blocks",
        "resource_guarding.moves_food",
        "resource_guarding.no_approach",
        "resource_guarding.uncertain",
        "resource_guarding.other",
    ),
    "human_interaction": (
        "human_interaction.usual",
        "human_interaction.seeking",
        "human_interaction.avoidant",
        "human_interaction.uncertain",
        "human_interaction.other",
    ),
    "animal_interaction": (
        "animal_interaction.usual",
        "animal_interaction.calm",
        "animal_interaction.avoidant",
        "animal_interaction.uncertain",
        "animal_interaction.other",
    ),
    "emotion": (
        "emotion.usual",
        "emotion.calm",
        "emotion.alert",
        "emotion.excited",
        "emotion.tense",
        "emotion.withdrawn",
        "emotion.seeking_interaction",
        "emotion.not_observed",
        "emotion.uncertain",
        "emotion.other",
    ),
    "walk": (
        "walk.usual",
        "walk.willing",
        "walk.exploring",
        "walk.reluctant",
        "walk.slow_or_stopping",
        "walk.tries_to_return",
        "walk.human_reaction",
        "walk.animal_reaction",
        "walk.not_done",
        "walk.not_observed",
        "walk.uncertain",
        "walk.other",
    ),
    "appearance_special_status": (
        "appearance.changed",
        "appearance.scratching",
        "appearance.red_area",
        "appearance.reduced_hair",
        "appearance.lying_long",
        "appearance.different_walk",
        "appearance.other",
        "appearance.not_observed",
        "appearance.uncertain",
    ),
}


def iter_platform_options() -> Iterable[tuple[str, str]]:
    for category, codes in PLATFORM_OPTIONS.items():
        for code in codes:
            yield category, code


async def seed_vocabulary(session) -> None:
    """Shared global vocabulary only; never creates organizations or identities."""
    from services.api.app.persistence.models.observation import (
        ObservationCategory,
        ObservationOption,
    )
    from sqlalchemy import select

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
                description="本機非診斷性照護觀察語彙",
                status="active",
            )
            session.add(category)
            await session.flush()
        category.display_name = CATEGORY_NAMES[category_code]
        for code in codes:
            option = await session.scalar(
                select(ObservationOption).where(
                    ObservationOption.category_id == category.id, ObservationOption.code == code
                )
            )
            label = OPTION_NAMES.get(
                code.rsplit(".", 1)[-1], code.rsplit(".", 1)[-1].replace("_", "／")
            )
            if option is None:
                option = ObservationOption(
                    category_id=category.id,
                    organization_id=None,
                    code=code,
                    display_name=label,
                    status="active",
                    requires_note=code.endswith(".other"),
                )
                session.add(option)
            option.display_name = label
            option.description = "本機展示選項"
        await session.flush()


def main() -> None:
    for category, code in iter_platform_options():
        print(f"{category}\t{code}")


if __name__ == "__main__":
    main()
