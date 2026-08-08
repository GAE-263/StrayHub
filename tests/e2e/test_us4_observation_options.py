from pathlib import Path

from services.api.app.application.effective_observation_service import EffectiveOption
from services.api.app.application.line_message_presenter import quick_reply_for_options


def test_us4_independent_surface_and_history_regression() -> None:
    page = Path("apps/web/app/(management)/settings/observation-options/page.tsx").read_text()
    model = Path("services/api/app/persistence/models/care_report.py").read_text()
    timeline = Path("services/api/app/api/animal_timeline.py").read_text()
    assert "平台預設" in page
    assert "停用" in page
    assert "answer_snapshots" in model
    assert "observation_snapshots" in timeline

    payload = quick_reply_for_options(
        [EffectiveOption("emotion.us4", "管理後的新名稱")],
        draft_token="us4-draft",
        step="emotion",
    )
    action = payload["quickReply"]["items"][0]["action"]
    assert action["displayText"] == "管理後的新名稱"
    assert "value=emotion.us4" in action["data"]
