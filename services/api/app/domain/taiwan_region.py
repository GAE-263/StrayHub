"""Canonical Taiwan county/city names used by public volunteer discovery."""

from __future__ import annotations

TAIWAN_REGIONS = (
    "臺北市",
    "新北市",
    "桃園市",
    "臺中市",
    "臺南市",
    "高雄市",
    "基隆市",
    "新竹市",
    "嘉義市",
    "新竹縣",
    "苗栗縣",
    "彰化縣",
    "南投縣",
    "雲林縣",
    "嘉義縣",
    "屏東縣",
    "宜蘭縣",
    "花蓮縣",
    "臺東縣",
    "澎湖縣",
    "金門縣",
    "連江縣",
)


def canonical_taiwan_region(value: str | None) -> str | None:
    """Return a canonical county/city or omit unstructured service areas."""

    if value is None:
        return None
    normalized = value.strip().replace("台", "臺")
    return normalized if normalized in TAIWAN_REGIONS else None
