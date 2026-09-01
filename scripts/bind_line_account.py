"""把 LINE 使用者（LINE userId）綁定到既有 StrayHub 帳號。

用途：工作人員／志工要用 LINE 串接自己的帳號時，先在這裡建立
line_user_bindings 記錄。綁定後，該 LINE UID 打 webhook 或走 /v1/line/bind
就會對應到這個 StrayHub 使用者，並依其角色切換 Rich Menu。

  # 綁定（把 LINE UID 綁到帳號 local-staff-a）
  uv run python -m scripts.bind_line_account bind \
    --username local-staff-a --line-user-id U1234567890abcdef...

  # 查詢某 LINE UID 目前綁到誰
  uv run python -m scripts.bind_line_account status --line-user-id U1234...

  # 查詢某帳號目前綁哪個 LINE UID
  uv run python -m scripts.bind_line_account status --username local-staff-a

  # 解綁
  uv run python -m scripts.bind_line_account unbind --line-user-id U1234...

注意：LINE userId 是「U」開頭的 33 字元字串，來自 LINE Login／Webhook，
不是 LINE 顯示名稱、也不是 @官方帳號 ID。取得方式見 docs/line-account-setup.md。
"""

from __future__ import annotations

import argparse
import asyncio

from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.models.identity import LineUserBinding
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)


def _valid_line_user_id(value: str) -> bool:
    return value.startswith("U") and 20 <= len(value) <= 128


async def _bind(username: str, line_user_id: str) -> None:
    async with session_factory() as session:
        repo = AuthenticationRepository(session)
        user = await repo.find_user_by_username(username)
        if user is None:
            print(f"[錯誤] 找不到帳號：{username}")
            return
        await repo.set_authentication_user_scope(user.id)

        existing = await repo.get_line_binding(line_user_id)
        if existing is not None:
            if existing.user_id == user.id:
                print(f"[略過] 此 LINE UID 已綁定到 {username}，無需重複。")
                return
            print(
                f"[錯誤] 此 LINE UID 已綁定到其他帳號（user_id={existing.user_id}）。"
                f"請先 unbind 再綁定，避免一個 LINE 帳號對應多個使用者。"
            )
            return

        already = await repo.get_line_binding_for_user(user.id)
        if already is not None:
            print(
                f"[注意] {username} 已綁過另一個 LINE UID（{already.line_user_id}）。"
                f"一個帳號通常只綁一個 LINE UID；如需更換請先 unbind 舊的。"
            )
            return

        await repo.add(LineUserBinding(line_user_id=line_user_id, user_id=user.id, status="active"))

        memberships = await repo.memberships(user.id, active_only=True)
        await session.commit()
        print(f"[成功] 已把 LINE UID 綁定到 {username}。")
        if len(memberships) != 1:
            print(
                f"[提醒] 此帳號目前有 {len(memberships)} 個 active membership。"
                f" Webhook 需要剛好 1 個，否則會要求『在 LIFF 明確選擇收容所』。"
            )


async def _unbind(line_user_id: str) -> None:
    async with session_factory() as session:
        repo = AuthenticationRepository(session)
        binding = await repo.get_line_binding(line_user_id)
        if binding is None:
            print("[略過] 查無此 LINE UID 的綁定。")
            return
        await session.delete(binding)
        await session.commit()
        print("[成功] 已解除綁定。")


async def _status(username: str | None, line_user_id: str | None) -> None:
    async with session_factory() as session:
        repo = AuthenticationRepository(session)
        if line_user_id:
            binding = await repo.get_line_binding(line_user_id)
            if binding is None:
                print("此 LINE UID 尚未綁定任何帳號。")
                return
            user = await repo.get_user(binding.user_id)
            print(
                f"LINE UID → 帳號：{user.username if user else binding.user_id}"
                f"（狀態 {binding.status}）"
            )
        elif username:
            user = await repo.find_user_by_username(username)
            if user is None:
                print(f"找不到帳號：{username}")
                return
            binding = await repo.get_line_binding_for_user(user.id)
            if binding is None:
                print(f"{username} 尚未綁定任何 LINE UID。")
                return
            print(f"{username} → LINE UID：{binding.line_user_id}（狀態 {binding.status}）")


def main() -> None:
    parser = argparse.ArgumentParser(description="StrayHub LINE 帳號綁定工具")
    sub = parser.add_subparsers(dest="action", required=True)

    p_bind = sub.add_parser("bind", help="綁定 LINE UID 到既有帳號")
    p_bind.add_argument("--username", required=True)
    p_bind.add_argument("--line-user-id", required=True)

    p_unbind = sub.add_parser("unbind", help="解除某 LINE UID 的綁定")
    p_unbind.add_argument("--line-user-id", required=True)

    p_status = sub.add_parser("status", help="查詢綁定狀態")
    p_status.add_argument("--username")
    p_status.add_argument("--line-user-id")

    args = parser.parse_args()

    if args.action in {"bind", "unbind"} and not _valid_line_user_id(args.line_user_id):
        parser.error("line-user-id 必須是 'U' 開頭的 LINE userId（約 33 字元）")

    if args.action == "bind":
        asyncio.run(_bind(args.username, args.line_user_id))
    elif args.action == "unbind":
        asyncio.run(_unbind(args.line_user_id))
    elif args.action == "status":
        if not args.username and not args.line_user_id:
            parser.error("status 需要 --username 或 --line-user-id 其中之一")
        asyncio.run(_status(args.username, args.line_user_id))


if __name__ == "__main__":
    main()
