"""Compile copy.yaml into copy.js, which the preview loads as a plain script.

interactive.html is never rewritten: it holds only rendering logic and loads
the data beside it. Wording, colours, glyphs, step names and the demo animals
all live in copy.yaml, so changing any of them touches one file and needs no
edit to the page.

The one place behaviour still depends on a label — which stool answer skips the
photo — is declared in copy.yaml and verified here, because a rename used to
silently make the app demand a photo when there was nothing to photograph.

    python build_preview.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).parent
SOURCE = HERE / "copy.yaml"
TARGET = HERE / "copy.js"

TONES = {"butter", "leaf", "peach", "sky", "lilac"}


def fail(message: str) -> None:
    print(f"copy.yaml 有問題：{message}", file=sys.stderr)
    raise SystemExit(1)


def check_boolean_keys(node, path: str = "") -> None:
    """YAML 1.1 turns bare yes/no/on/off keys into booleans.

    A key written as `no:` silently becomes False, so the value can never be
    looked up by name again — the confirm buttons rendered blank because of
    exactly this. Refuse to build rather than ship an invisible break.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, bool):
                fail(
                    f"{path} 有個鍵被 YAML 當成布林值了（yes/no/on/off 要加引號，"
                    f'例如寫成 "no": 或改名成 reject）'
                )
            check_boolean_keys(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            check_boolean_keys(item, f"{path}[{index}]")


def validate(copy: dict) -> None:
    check_boolean_keys(copy)

    questions = copy.get("questions") or []
    if not questions:
        fail("questions 是空的")

    for question in questions:
        for field in ("key", "icon", "title", "options"):
            if field not in question:
                fail(f"題目 {question.get('key', '?')} 少了 {field}")
        if not question["options"]:
            fail(f"題目 {question['title']} 沒有任何選項")
        for option in question["options"]:
            if not isinstance(option, list) or len(option) != 2:
                fail(f"題目 {question['title']} 的選項要寫成 [\"文字\", \"圖示\"]")

        # The one place logic still depends on a label: say so loudly rather
        # than letting a rename quietly change who gets asked for a photo.
        marker = question.get("stool_photo_unless")
        if marker is not None:
            labels = [option[0] for option in question["options"]]
            if marker not in labels:
                fail(
                    f"stool_photo_unless 寫的是「{marker}」，"
                    f"但 {question['title']} 的選項只有：{'、'.join(labels)}"
                )

    for section in (
        "menu", "find_dog", "qr_scan", "search", "overview", "confirm", "stool_photo",
        "portrait_photo", "note", "story", "summary", "done", "tones", "glyphs",
        "steps", "demo_dogs",
    ):
        if section not in copy:
            fail(f"少了 {section} 區塊")

    for name, tone in copy["tones"].items():
        if tone not in TONES:
            fail(f"tones.{name} 寫的是「{tone}」，只能填：{'、'.join(sorted(TONES))}")


def main() -> None:
    copy = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    validate(copy)

    TARGET.write_text(
        "// 由 copy.yaml 產生，不要直接改這個檔案。\n"
        "// 改文案請編輯 copy.yaml，然後執行：python build_preview.py\n"
        f"window.COPY = {json.dumps(copy, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )

    total = sum(len(q["options"]) for q in copy["questions"])
    print(f"已產生 {TARGET.name}：{len(copy['questions'])} 題、{total} 個選項")


if __name__ == "__main__":
    main()
