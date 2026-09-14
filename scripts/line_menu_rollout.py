"""Exact reviewed menu switches; no publication, membership edits or bulk API.

Plans contain private external identities and must never be logged or uploaded
as public CI artifacts. Receipts contain only target hashes and menu mappings.
There is no automatic retry, including after an uncertain HTTP outcome.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from scripts.line_menu_manifest import VerifiedMenuManifest, canonical_json
from scripts.line_rollout_config import unique
from scripts.production_config_sync import ConfigSyncError, atomic_write

UID = re.compile(r"U[0-9a-f]{32}")
MENU = re.compile(r"richmenu-[A-Za-z0-9-]+")


class RolloutError(ValueError):
    pass


class MenuClient(Protocol):
    def read(self, target: str) -> str | None: ...
    def switch(self, target: str, menu: str | None) -> None: ...
    def verify(self, manifest: VerifiedMenuManifest) -> None: ...


def target_path(target: str) -> str:
    if target == "default":
        return "/v2/bot/user/all/richmenu"
    if not UID.fullmatch(target):
        raise RolloutError("invalid_target")
    return f"/v2/bot/user/{target}/richmenu"


class LineClient:
    """Fixed hosts, no proxies/redirects/retries; response bodies never logged."""

    def __init__(self, token: str):
        if not token or any(c.isspace() for c in token):
            raise RolloutError("invalid_credential")
        self._token = token

    def request(self, method: str, path: str, *, data: bool = False) -> tuple[int, bytes]:
        target = r"/v2/bot/user/(?:all|U[0-9a-f]{32})/richmenu"
        menu = r"richmenu-[A-Za-z0-9-]+"
        allowed = (
            (
                data
                and method == "GET"
                and re.fullmatch(r"/v2/bot/richmenu/" + menu + "/content", path)
            )
            or (
                not data
                and method == "GET"
                and (
                    path == "/v2/bot/info"
                    or re.fullmatch(r"/v2/bot/richmenu/" + menu, path)
                    or re.fullmatch(target, path)
                )
            )
            or (not data and method == "POST" and re.fullmatch(target + "/" + menu, path))
            or (not data and method == "DELETE" and re.fullmatch(target, path))
        )
        if not allowed:
            raise RolloutError("endpoint_not_allowed")
        connection = http.client.HTTPSConnection(
            "api-data.line.me" if data else "api.line.me", timeout=20
        )
        try:
            connection.request(method, path, headers={"Authorization": f"Bearer {self._token}"})
            response = connection.getresponse()
            body = response.read(3_000_001)
            if len(body) > 3_000_000:
                raise RolloutError("response_too_large")
            return response.status, body
        except (OSError, http.client.HTTPException):
            raise RolloutError("transport_outcome_unknown") from None
        finally:
            connection.close()

    def read(self, target: str) -> str | None:
        status, raw = self.request("GET", target_path(target))
        if status == 404:
            return None
        if status != 200:
            raise RolloutError("readback_failed")
        try:
            value = json.loads(raw, object_pairs_hook=unique)["richMenuId"]
            if not isinstance(value, str) or not MENU.fullmatch(value):
                raise ValueError
            return value
        except (ValueError, KeyError, TypeError, ConfigSyncError):
            raise RolloutError("invalid_readback") from None

    def switch(self, target: str, menu: str | None) -> None:
        path = target_path(target)
        if menu is not None:
            if not MENU.fullmatch(menu):
                raise RolloutError("invalid_menu")
            method, path = "POST", path + "/" + menu
        else:
            method = "DELETE"  # Exact binding/default removal, never resource deletion.
        status, _ = self.request(method, path)
        if status != 200:
            raise RolloutError("mutation_outcome_unknown")

    def verify(self, manifest: VerifiedMenuManifest) -> None:
        status, raw = self.request("GET", "/v2/bot/info")
        try:
            bot = json.loads(raw, object_pairs_hook=unique)
            if (
                status != 200
                or bot["basicId"] != manifest.bot_basic_id
                or hashlib.sha256(bot["userId"].encode()).hexdigest() != manifest.bot_fingerprint
            ):
                raise ValueError
            for menu in manifest.menus.values():
                status, raw = self.request("GET", "/v2/bot/richmenu/" + menu["id"])
                definition = json.loads(raw, object_pairs_hook=unique)
                if definition.pop("richMenuId", None) != menu["id"] or status != 200:
                    raise ValueError
                # Same canonical representation as resource publication.
                if (
                    hashlib.sha256(canonical_json(definition)).hexdigest()
                    != menu["definition_sha256"]
                ):
                    raise ValueError
                status, raw = self.request(
                    "GET", "/v2/bot/richmenu/" + menu["id"] + "/content", data=True
                )
                if status != 200 or hashlib.sha256(raw).hexdigest() != menu["image_sha256"]:
                    raise ValueError
        except (ValueError, KeyError, TypeError, AttributeError, ConfigSyncError):
            raise RolloutError("resource_identity_mismatch") from None


def plan_switches(
    client: MenuClient, manifest: VerifiedMenuManifest, intents: list[dict], *, source: str
) -> dict:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", source):
        raise RolloutError("authorization_source_required")
    if not isinstance(intents, list) or not 1 <= len(intents) <= 20:
        raise RolloutError("batch_size")
    targets: set[str] = set()
    entries = []
    for intent in intents:
        if not isinstance(intent, dict) or set(intent) != {"target", "role"}:
            raise RolloutError("invalid_intent")
        target, role = intent["target"], intent["role"]
        target_path(target)
        if target in targets or role not in {"default", "volunteer"}:
            raise RolloutError("invalid_intent")
        if target == "default" and (role != "default" or len(intents) != 1):
            raise RolloutError("default_requires_separate_plan")
        targets.add(target)
        entries.append(
            {"target": target, "before": client.read(target), "after": manifest.menus[role]["id"]}
        )
    client.verify(manifest)
    return {
        "schema_version": 1,
        "operation": "menu-switch",
        "git_sha": manifest.git_sha,
        "manifest_sha256": manifest.manifest_sha256,
        "authorization_source": source,
        "entries": entries,
    }


def validate_plan(plan: dict, manifest: VerifiedMenuManifest) -> None:
    if set(plan) != {
        "schema_version",
        "operation",
        "git_sha",
        "manifest_sha256",
        "authorization_source",
        "entries",
    }:
        raise RolloutError("invalid_plan")
    if (
        plan["schema_version"] != 1
        or plan["operation"] not in {"menu-switch", "menu-restore"}
        or plan["git_sha"] != manifest.git_sha
        or plan["manifest_sha256"] != manifest.manifest_sha256
        or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", plan["authorization_source"])
    ):
        raise RolloutError("plan_identity")
    entries = plan["entries"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= 20:
        raise RolloutError("batch_size")
    seen: set[str] = set()
    for entry in entries:
        if set(entry) != {"target", "before", "after"}:
            raise RolloutError("invalid_entry")
        target_path(entry["target"])
        if entry["target"] in seen or (entry["target"] == "default" and len(entries) != 1):
            raise RolloutError("duplicate_target")
        seen.add(entry["target"])
        for value in (entry["before"], entry["after"]):
            if value is not None and (not isinstance(value, str) or not MENU.fullmatch(value)):
                raise RolloutError("invalid_menu")
        if plan["operation"] == "menu-switch":
            roles = ("default",) if entry["target"] == "default" else ("default", "volunteer")
            if entry["after"] not in {manifest.menus[role]["id"] for role in roles}:
                raise RolloutError("unpublished_menu")


def target_hash(target: str) -> str:
    return hashlib.sha256(target.encode()).hexdigest()


def apply_plan(
    client: MenuClient,
    manifest: VerifiedMenuManifest,
    plan: dict,
    *,
    receipt: Path,
    authorize: Callable[[], None],
    uid: int,
    gid: int,
) -> dict:
    validate_plan(plan, manifest)
    if receipt.exists() or receipt.is_symlink():
        raise RolloutError("receipt_exists_readback_and_replan")
    authorize()
    client.verify(manifest)
    # Reject an entire stale batch before the first mutation.
    for entry in plan["entries"]:
        if client.read(entry["target"]) != entry["before"]:
            raise RolloutError("binding_drift")
    ledger: dict = {
        "schema_version": 1,
        "plan_sha256": hashlib.sha256(canonical_json(plan)).hexdigest(),
        "status": "in-progress",
        "entries": [],
    }

    def persist() -> None:
        atomic_write(receipt, canonical_json(ledger), uid=uid, gid=gid, mode=0o600)

    persist()
    try:
        for entry in plan["entries"]:
            authorize()
            if client.read(entry["target"]) != entry["before"]:
                raise RolloutError("binding_drift")
            record = {
                "target_sha256": target_hash(entry["target"]),
                "before": entry["before"],
                "after": entry["after"],
                "status": "intent-recorded",
            }
            ledger["entries"].append(record)
            persist()  # Write-ahead intent survives interruption after HTTP request.
            if entry["before"] != entry["after"]:
                client.switch(entry["target"], entry["after"])
            if client.read(entry["target"]) != entry["after"]:
                raise RolloutError("readback_mismatch")
            record["status"] = "verified"
            persist()
        ledger["status"] = "success"
        persist()
        return ledger
    except BaseException:
        ledger["status"] = "stopped-readback-required"
        persist()
        raise


def restoration_plan(
    client: MenuClient, manifest: VerifiedMenuManifest, original: dict, receipt: dict
) -> dict:
    validate_plan(original, manifest)
    if receipt.get("plan_sha256") != hashlib.sha256(canonical_json(original)).hexdigest():
        raise RolloutError("receipt_identity")
    attempted = {entry["target_sha256"] for entry in receipt["entries"]}
    entries = []
    for entry in original["entries"]:
        if target_hash(entry["target"]) not in attempted:
            continue
        current = client.read(entry["target"])
        if current not in (entry["before"], entry["after"]):
            raise RolloutError("binding_drift")
        if current != entry["before"]:
            entries.append({"target": entry["target"], "before": current, "after": entry["before"]})
    if not entries:
        raise RolloutError("nothing_to_restore")
    return {**original, "operation": "menu-restore", "entries": entries}
