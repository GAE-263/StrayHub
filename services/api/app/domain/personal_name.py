"""Surname extraction for management-facing volunteer identification.

Only the surname leaves the encrypted PII store, so care history can name who
reported without a PII reveal.
"""

from __future__ import annotations

# Two-character Chinese surnames; without these "歐陽" would show as "歐".
COMPOUND_SURNAMES = frozenset(
    {
        "歐陽",
        "司馬",
        "諸葛",
        "上官",
        "皇甫",
        "端木",
        "東方",
        "南宮",
        "尉遲",
        "長孫",
        "宇文",
        "慕容",
        "夏侯",
        "公孫",
        "令狐",
        "澹台",
        "軒轅",
        "太史",
        "申屠",
        "獨孤",
        "萬俟",
        "聞人",
        "赫連",
        "第五",
    }
)

MAX_SURNAME_LENGTH = 20


def surname_of(full_name: str | None) -> str | None:
    """Return the surname, or None when it cannot be determined."""
    if full_name is None:
        return None
    name = " ".join(full_name.split())
    if not name:
        return None
    # A space means a Western-ordered name, where the surname trails.
    if " " in name:
        return name.rsplit(" ", 1)[-1][:MAX_SURNAME_LENGTH]
    if name[:2] in COMPOUND_SURNAMES:
        return name[:2]
    return name[0]
