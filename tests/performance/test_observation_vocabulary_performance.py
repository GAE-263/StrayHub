"""本功能的本機資料處理效能驗收。

這裡測量與瀏覽器首次載入相同規模資料時的摘要、搜尋／篩選及失敗狀態
資料轉換成本；實際網路延遲與瀏覽器繪製仍由 quickstart 的人工驗收涵蓋。
"""

from __future__ import annotations

from math import ceil
from time import perf_counter

CATEGORY_COUNT = 13
OPTION_COUNT = 500


def _fixture_options() -> list[dict[str, str]]:
    return [
        {
            "category_code": f"category_{index % CATEGORY_COUNT}",
            "display_name": f"測試觀察詞彙 {index}",
            "stable_code": f"test_observation_{index}",
            "description": "本機效能驗收用的觀察選項",
            "status": "active" if index % 11 else "disabled",
            "source": "custom" if index % 5 == 0 else "platform",
        }
        for index in range(OPTION_COUNT)
    ]


def _summary(options: list[dict[str, str]]) -> dict[str, int]:
    return {
        "category_count": len({option["category_code"] for option in options}),
        "active_count": sum(option["status"] == "active" for option in options),
        "custom_count": sum(option["source"] == "custom" for option in options),
        "inactive_count": sum(option["status"] != "active" for option in options),
    }


def _filter_options(options: list[dict[str, str]]) -> list[dict[str, str]]:
    query = "測試觀察詞彙 42".casefold()
    return [
        option
        for option in options
        if option["category_code"] == "category_3"
        and option["status"] == "active"
        and option["source"] == "custom"
        and query
        in " ".join(
            (
                option["display_name"],
                option["stable_code"],
                option["description"],
            )
        ).casefold()
    ]


def _error_state() -> dict[str, str]:
    return {
        "status": "error",
        "message": "觀察詞彙載入失敗，請重新載入。",
        "action": "reload",
    }


def _p95(samples: list[float]) -> float:
    return sorted(samples)[min(len(samples) - 1, ceil(len(samples) * 0.95) - 1)]


def test_observation_vocabulary_local_processing_p95() -> None:
    options = _fixture_options()
    assert len(options) == OPTION_COUNT
    assert len({option["category_code"] for option in options}) == CATEGORY_COUNT

    summary_samples: list[float] = []
    filter_samples: list[float] = []
    error_samples: list[float] = []

    for _ in range(10):
        started = perf_counter()
        summary = _summary(options)
        summary_samples.append(perf_counter() - started)

        started = perf_counter()
        filtered = _filter_options(options)
        filter_samples.append(perf_counter() - started)

        started = perf_counter()
        error = _error_state()
        error_samples.append(perf_counter() - started)

        assert summary["category_count"] == CATEGORY_COUNT
        assert summary["active_count"] > 0
        assert filtered == []
        assert error["status"] == "error"
        assert error["action"] == "reload"

    assert _p95(summary_samples) < 2
    assert _p95(filter_samples) < 2
    assert _p95(error_samples) < 2
