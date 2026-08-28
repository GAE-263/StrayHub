"""Interactive local chat demo for the 領養媒合 (adoption matching) LINE Bot.

There is no real LINE channel wired up for local development, so this script
talks directly to the running FastAPI server's real `POST /v1/line/webhook`
endpoint over HTTP — the exact same code path a real LINE webhook event
would hit (signature verification, idempotency, the domain state machine,
persistence, matching). The only thing standing in for LINE itself is the
reply transport: `line_webhook.py` already switches to an in-memory
`MockLineAdapter` whenever `LINE_CHANNEL_ACCESS_TOKEN` looks like the local
placeholder (starts with "fake-"), and the webhook response includes what
that adapter captured as `debug_replies` — that's what this script renders.

Prerequisites:
  - `uv run python -m uvicorn services.api.app.main:app --port 8001` running
  - At least one animal with `is_adoptable=true` in some active organization
    (use the management UI's "編輯領養資料" dialog, or the
    `PATCH /v1/management/animals/{id}/adoption-profile` endpoint)

Usage:
  uv run python -m scripts.adoption_chat_demo
  uv run python -m scripts.adoption_chat_demo --base-url http://127.0.0.1:8001
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import secrets
import sys
from uuid import uuid4

import httpx
from services.api.app.config.settings import get_settings


def _sign(body: bytes, secret: str) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def _postback_event(line_user_id: str, data: str) -> dict:
    return {
        "type": "postback",
        "webhookEventId": uuid4().hex,
        "replyToken": uuid4().hex,
        "source": {"userId": line_user_id},
        "postback": {"data": data},
    }


def _text_event(line_user_id: str, text: str) -> dict:
    return {
        "type": "message",
        "webhookEventId": uuid4().hex,
        "replyToken": uuid4().hex,
        "source": {"userId": line_user_id},
        "message": {"type": "text", "id": uuid4().hex, "text": text},
    }


def _print_message(message: dict) -> None:
    kind = message.get("type")
    if kind == "text":
        print(f"\n🐾  {message['text']}")
    elif kind == "image":
        print("\n🐾  [傳送了一張照片]")
    elif kind == "template":
        template = message.get("template", {})
        if template.get("text"):
            print(f"\n🐾  {template['text']}")
    else:
        print(f"\n🐾  [{kind} 訊息]")


def _collect_options(messages: list[dict]) -> list[tuple[str, str]]:
    """Return [(label, postback_data), ...] offered by this turn's messages."""
    options: list[tuple[str, str]] = []
    for message in messages:
        quick_reply = message.get("quickReply")
        if quick_reply:
            for item in quick_reply.get("items", []):
                action = item.get("action", {})
                if action.get("type") == "postback":
                    options.append((action.get("label", "?"), action["data"]))
        template = message.get("template")
        if template and template.get("type") == "buttons":
            for action_wrapper in template.get("actions", []):
                action = action_wrapper.get("action", {})
                if action.get("type") == "postback":
                    options.append((action.get("label", "?"), action["data"]))
    return options


def _looks_terminal(messages: list[dict]) -> bool:
    joined = " ".join(m.get("text", "") for m in messages if m.get("type") == "text")
    return "已收到您的領養意願" in joined or "已取消這次領養媒合對話" in joined


def run(base_url: str) -> None:
    settings = get_settings()
    if not settings.line_channel_access_token.startswith("fake-"):
        print(
            "LINE_CHANNEL_ACCESS_TOKEN 看起來不是本機假值，"
            "為了避免對真正的 LINE 頻道送出請求，這個腳本只在本機假值下執行。",
            file=sys.stderr,
        )
        raise SystemExit(1)

    line_user_id = f"Udemo{secrets.token_hex(8)}"
    print(f"（模擬 LINE 使用者：{line_user_id}，每次執行都是全新身分）")
    print("=" * 48)

    client = httpx.Client(timeout=10)
    event = _postback_event(line_user_id, "action=start_adoption_matching&flow=adoption")

    while True:
        body = json.dumps({"events": [event]}).encode("utf-8")
        signature = _sign(body, settings.line_channel_secret)
        response = client.post(
            f"{base_url}/v1/line/webhook",
            content=body,
            headers={"X-Line-Signature": signature, "Content-Type": "application/json"},
        )
        if response.status_code != 200:
            print(f"\n⚠️  伺服器回應 HTTP {response.status_code}：{response.text}")
            return
        data = response.json()
        result = data["event_results"][0]
        if result["status"] == "rejected":
            print(f"\n⚠️  {result.get('reason')}")
            print("（常見原因：目前沒有任何 is_adoptable=true 的動物，或伺服器未啟動）")
            return

        all_messages: list[dict] = [m for batch in data.get("debug_replies", []) for m in batch]
        for message in all_messages:
            _print_message(message)

        if _looks_terminal(all_messages):
            print("\n" + "=" * 48)
            again = input("對話已結束。要用新的身分再跑一次嗎？(y/N) ").strip().lower()
            if again == "y":
                line_user_id = f"Udemo{secrets.token_hex(8)}"
                print(f"（新身分：{line_user_id}）")
                event = _postback_event(
                    line_user_id, "action=start_adoption_matching&flow=adoption"
                )
                continue
            return

        options = _collect_options(all_messages)
        try:
            if options:
                print()
                for index, (label, _data) in enumerate(options, start=1):
                    print(f"  {index}. {label}")
                choice = input("請輸入選項編號： ").strip()
                if not choice.isdigit() or not (1 <= int(choice) <= len(options)):
                    print("（不是有效的選項編號，請重新輸入）")
                    continue
                event = _postback_event(line_user_id, options[int(choice) - 1][1])
            else:
                text = input("請輸入文字（例如手機號碼）： ").strip()
                if not text:
                    continue
                event = _text_event(line_user_id, text)
        except (EOFError, KeyboardInterrupt):
            print("\n再見！")
            return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    run(args.base_url)


if __name__ == "__main__":
    main()
