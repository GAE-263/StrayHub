from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from services.api.app.application.growth_diary_ai_analysis_service import (
    GrowthDiaryAiAnalysisService,
)
from services.api.app.infrastructure.ai.gemini_client import GeminiGrowthDiaryAnalysis


def _fake_result() -> GeminiGrowthDiaryAnalysis:
    return GeminiGrowthDiaryAnalysis(mood="positive", adopter_reply="很好", staff_summary="良好")


@pytest.mark.asyncio
async def test_no_note_and_no_photo_skips_the_gemini_call_entirely() -> None:
    gemini = AsyncMock()

    result = await GrowthDiaryAiAnalysisService(gemini).analyze_entry(
        animal_name="小白", note=None, photo=None
    )

    assert result is None
    gemini.analyze_growth_diary_entry.assert_not_called()


@pytest.mark.asyncio
async def test_photo_only_entry_is_analyzed_via_multimodal_call() -> None:
    """The point of this feature: a photo with no text note used to skip
    analysis entirely — it should now still reach Gemini, with the image
    bytes passed through."""
    gemini = AsyncMock()
    gemini.analyze_growth_diary_entry.return_value = _fake_result()
    photo = b"jpeg-bytes"

    result = await GrowthDiaryAiAnalysisService(gemini).analyze_entry(
        animal_name="小白", note=None, photo=photo, photo_mime_type="image/jpeg"
    )

    assert result is not None
    gemini.analyze_growth_diary_entry.assert_awaited_once()
    _, kwargs = gemini.analyze_growth_diary_entry.await_args
    assert kwargs["image"] == photo
    assert kwargs["image_mime_type"] == "image/jpeg"
    # The photo-only prompt must actually ask Gemini to look at the image
    # rather than referencing text content that doesn't exist.
    prompt = gemini.analyze_growth_diary_entry.await_args.args[0]
    assert "沒有附加文字說明" in prompt


@pytest.mark.asyncio
async def test_note_only_entry_still_works_without_a_photo() -> None:
    gemini = AsyncMock()
    gemini.analyze_growth_diary_entry.return_value = _fake_result()

    result = await GrowthDiaryAiAnalysisService(gemini).analyze_entry(
        animal_name="小白", note="今天吃得很好", photo=None
    )

    assert result is not None
    _, kwargs = gemini.analyze_growth_diary_entry.await_args
    assert kwargs["image"] is None


@pytest.mark.asyncio
async def test_note_and_photo_together_mentions_both_in_the_prompt() -> None:
    gemini = AsyncMock()
    gemini.analyze_growth_diary_entry.return_value = _fake_result()

    await GrowthDiaryAiAnalysisService(gemini).analyze_entry(
        animal_name="小白",
        note="今天散步很開心",
        photo=b"bytes",
        photo_mime_type="image/png",
    )

    prompt = gemini.analyze_growth_diary_entry.await_args.args[0]
    assert "今天散步很開心" in prompt
    assert "同時附上一張照片" in prompt


@pytest.mark.asyncio
async def test_prompt_instructs_answering_adoption_related_questions() -> None:
    """The adopter_reply instruction must actively answer adoption/care
    questions with real guidance (not just sympathy) — the stated goal is
    helping new adopters through the adjustment period and reducing
    abandonment, so the prompt has to say so explicitly rather than leaving
    it to Gemini's own judgment call on a generic "warm reply" ask."""
    gemini = AsyncMock()
    gemini.analyze_growth_diary_entry.return_value = _fake_result()

    await GrowthDiaryAiAnalysisService(gemini).analyze_entry(
        animal_name="小白", note="牠一直吠叫該怎麼辦？", photo=None
    )

    prompt = gemini.analyze_growth_diary_entry.await_args.args[0]
    assert "必須」根據正確的飼養知識具體回答" in prompt
    assert "降低棄養風險" in prompt
