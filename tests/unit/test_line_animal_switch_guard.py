"""志工回到選單重選動物時，不該撞牆，也不該讓上一隻的回報被無聲改寫。

圖文選單、QR 掃描、今日名單、文字搜尋這四條路進來的 `confirm_animal` 都不帶
`draft_token`。若志工手上還有一筆未完成的草稿：

* 選到「同一隻」——他的意思是「繼續」，但 `begin_reselection` 會以
  `same_animal`(422) 擋下，整個流程死在錯誤卡片上。
* 選到「不同隻」——舊草稿會被直接改綁到新動物、照片全刪、心得搬家，志工事前
  完全不知情。前一隻的照護紀錄就這樣消失。

所以：同一隻要能續填，不同隻要先問過人。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from services.api.app.api import line_webhook
from services.api.app.domain.line_care_report_state import DraftState


class _FakeAnimalRepository:
    animals: dict[UUID, SimpleNamespace] = {}

    def __init__(self, session, organization_id) -> None:
        self.organization_id = organization_id

    async def get(self, animal_id):
        return self.animals.get(animal_id)


class _FakeScopeRepository:
    def __init__(self, session, organization_id) -> None:
        pass

    async def is_animal_reportable(self, *, animal_id, volunteer_user_id) -> bool:
        return True


class _FakeDraftRepository:
    draft: SimpleNamespace | None = None
    cleared: list[UUID] = []

    def __init__(self, session, organization_id) -> None:
        self.organization_id = organization_id

    async def get_active_for_volunteer(self, volunteer_user_id):
        return self.draft

    async def get_by_token(self, token):
        return self.draft

    async def get(self, draft_id):
        return self.draft

    async def clear_media(self, draft_id) -> None:
        self.cleared.append(draft_id)


class _FakeLine:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def reply(self, *, reply_token: str, messages: list[dict]) -> None:
        self.messages.extend(messages)


_VOLUNTEER = uuid4()
_ORGANIZATION = uuid4()


def _animal(name: str) -> SimpleNamespace:
    animal = SimpleNamespace(id=uuid4(), name=name, status="active", shelter_number="A001")
    _FakeAnimalRepository.animals[animal.id] = animal
    return animal


def _draft(animal_id: UUID, volunteer_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        animal_id=animal_id,
        candidate_animal_id=None,
        volunteer_user_id=volunteer_id,
        status="active",
        current_step=DraftState.ANSWERING_GAIT.value,
        answers={"gait": "gait.normal"},
        reconfirmation_keys=[],
        modification_summary={},
        note="小黑今天走得很穩",
        story=None,
        answer_source_event_id=None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        last_interaction_at=None,
    )


def _postback_event(**data: str) -> dict:
    return {
        "replyToken": "reply-token",
        "webhookEventId": "event-1",
        "postback": {"data": "&".join(f"{key}={value}" for key, value in data.items())},
    }


@pytest.fixture()
def webhook(monkeypatch):
    """把 confirm_animal 這條路上的相依都換成假的，只留下要測的分支邏輯。"""
    _FakeAnimalRepository.animals = {}
    _FakeDraftRepository.draft = None
    _FakeDraftRepository.cleared = []
    calls: dict[str, object] = {}

    async def _fake_reply_next_step(session, line, event, **kwargs):
        calls["next_step"] = kwargs

    monkeypatch.setattr(line_webhook, "AnimalRepository", _FakeAnimalRepository)
    monkeypatch.setattr(line_webhook, "ReportableScopeRepository", _FakeScopeRepository)
    monkeypatch.setattr(line_webhook, "CareReportDraftRepository", _FakeDraftRepository)
    monkeypatch.setattr(line_webhook, "_reply_next_step", _fake_reply_next_step)
    monkeypatch.setattr(
        line_webhook, "get_settings", lambda: SimpleNamespace(draft_ttl_seconds=86400)
    )
    return calls


async def _confirm(line, **data):
    return await line_webhook._handle_postback(
        None,
        line,
        _postback_event(**data),
        user_id=_VOLUNTEER,
        organization_id=_ORGANIZATION,
        membership_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_picking_the_same_animal_continues_the_report_instead_of_erroring(webhook) -> None:
    animal = _animal("小黑")
    draft = _draft(animal.id, _VOLUNTEER)
    _FakeDraftRepository.draft = draft
    line = _FakeLine()

    await _confirm(line, action="confirm_animal", animal_id=str(animal.id))

    assert webhook["next_step"]["draft"] is draft
    assert "繼續回報 小黑" in json.dumps(
        webhook["next_step"]["prefix_messages"], ensure_ascii=False
    )
    # 續填，不是換一隻：草稿原封不動，照片也不能被清掉。
    assert draft.animal_id == animal.id
    assert draft.note == "小黑今天走得很穩"
    assert _FakeDraftRepository.cleared == []


@pytest.mark.asyncio
async def test_picking_another_animal_asks_before_discarding_the_unfinished_report(
    webhook,
) -> None:
    previous, other = _animal("小黑"), _animal("小白")
    draft = _draft(previous.id, _VOLUNTEER)
    _FakeDraftRepository.draft = draft
    line = _FakeLine()

    await _confirm(line, action="confirm_animal", animal_id=str(other.id))

    rendered = json.dumps(line.messages, ensure_ascii=False)
    assert "還有一筆回報沒送出" in rendered
    assert "繼續回報 小黑" in rendered and "改成回報 小白" in rendered
    assert "switch=1" in rendered
    # 沒按下確認之前，什麼都不能動。
    assert draft.animal_id == previous.id
    assert draft.note == "小黑今天走得很穩"
    assert _FakeDraftRepository.cleared == []
    assert "next_step" not in webhook


@pytest.mark.asyncio
async def test_confirming_the_switch_moves_the_draft_and_says_what_was_dropped(webhook) -> None:
    previous, other = _animal("小黑"), _animal("小白")
    draft = _draft(previous.id, _VOLUNTEER)
    _FakeDraftRepository.draft = draft
    line = _FakeLine()

    await _confirm(line, action="confirm_animal", animal_id=str(other.id), switch="1")

    assert draft.animal_id == other.id
    assert draft.note is None
    assert draft.reconfirmation_keys == ["gait"]
    assert _FakeDraftRepository.cleared == [draft.id]
    assert "照片與心得不會沿用" in json.dumps(
        webhook["next_step"]["prefix_messages"], ensure_ascii=False
    )


@pytest.mark.asyncio
async def test_reselect_animal_works_without_a_draft_token(webhook, monkeypatch) -> None:
    """摘要頁的「換一隻」在無 token 的草稿上也必須能按。"""
    animal = _animal("小黑")
    _FakeDraftRepository.draft = _draft(animal.id, _VOLUNTEER)
    line = _FakeLine()

    async def _fake_scoped_animals(session, organization_id, user_id):
        return [animal]

    monkeypatch.setattr(line_webhook, "_scoped_animals", _fake_scoped_animals)

    await _confirm(line, action="reselect_animal", draft_token="")

    assert "可回報動物" in json.dumps(line.messages, ensure_ascii=False)


@pytest.mark.asyncio
async def test_the_confirmation_step_never_leaves_the_bot_silent(monkeypatch) -> None:
    """第 1 題按「上一步」會回到 CONFIRMING_ANIMAL。

    `_reply_next_step` 原本沒有這個狀態的分支，最後又是 `if messages:`，所以志工
    按下去之後機器人一句話都不說——聊天室裡只剩上面那幾張過期的卡片可以點。
    """
    animal = _animal("小黑")
    draft = _draft(animal.id, _VOLUNTEER)
    draft.current_step = DraftState.CONFIRMING_ANIMAL.value
    line = _FakeLine()

    async def _fake_photo(session, animal_, organization_id):
        return None

    async def _fake_area(session, animal_, organization_id):
        return "後山第三犬舍"

    # 這個測試要跑真正的 _reply_next_step，所以不用 webhook fixture 的假替身。
    monkeypatch.setattr(line_webhook, "AnimalRepository", _FakeAnimalRepository)
    monkeypatch.setattr(line_webhook, "_animal_photo_message", _fake_photo)
    monkeypatch.setattr(line_webhook, "_animal_area_label", _fake_area)

    await line_webhook._reply_next_step(
        None,
        line,
        _postback_event(action="back"),
        organization_id=_ORGANIZATION,
        draft=draft,
        raw_token="",
    )

    rendered = json.dumps(line.messages, ensure_ascii=False)
    assert line.messages, "機器人不能一句話都不回"
    assert "是 小黑 嗎？" in rendered
    assert "confirm_animal" in rendered


def test_a_failed_photo_still_offers_the_button_its_text_promises() -> None:
    for subject, action in (("stool", "skip_stool_media"), ("portrait", "skip_media")):
        rendered = json.dumps(line_webhook._media_failure_bubble(subject), ensure_ascii=False)
        assert "略過照片" in rendered
        assert f"action={action}" in rendered


@pytest.mark.asyncio
async def test_changing_your_mind_about_changing_animal_is_not_an_error(webhook) -> None:
    """帶著 token 從摘要頁按「換一隻」又選回原本那隻，等於「算了」。"""
    animal = _animal("小黑")
    draft = _draft(animal.id, _VOLUNTEER)
    draft.current_step = DraftState.REVIEWING.value
    _FakeDraftRepository.draft = draft
    line = _FakeLine()

    await _confirm(
        line, action="confirm_animal", animal_id=str(animal.id), draft_token="a-real-token"
    )

    assert draft.animal_id == animal.id
    assert draft.note == "小黑今天走得很穩"
    assert "沒有更換" in json.dumps(webhook["next_step"]["prefix_messages"], ensure_ascii=False)
