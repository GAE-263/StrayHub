"""Narrow rollout settings for the existing atomic config-sync/preflight path."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.line_menu_manifest import VerifiedMenuManifest
from scripts.production_config_sync import ConfigSyncError, _safe_file


def unique(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ConfigSyncError("rollout", "duplicate_json_key")
        result[key] = value
    return result


def load_rollout(path: Path, manifest: VerifiedMenuManifest, *, production: bool) -> dict[str, str]:
    try:
        doc = json.loads(path.read_bytes(), object_pairs_hook=unique)
        return validate_rollout(doc, manifest, production=production)
    except (OSError, ValueError, KeyError, TypeError):
        raise ConfigSyncError("rollout", "invalid_rollout_configuration") from None


def validate_rollout(
    doc: dict, manifest: VerifiedMenuManifest, *, production: bool
) -> dict[str, str]:
    common = {"schema_version", "mode", "git_sha", "manifest_sha256", "channel_id"}
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        raise ValueError("schema")
    mode = doc.get("mode")
    extra = {
        "inert": set(),
        "bounded": {"user_sha256", "expires_at"},
        "global": {"report_path", "resources_path"},
    }
    if mode not in extra or set(doc) - {"ai"} != common | extra[mode]:
        raise ValueError("fields")
    if doc["git_sha"] != manifest.git_sha or doc["manifest_sha256"] != manifest.manifest_sha256:
        raise ValueError("identity")
    if not isinstance(doc["channel_id"], str) or not re.fullmatch(r"[0-9]+", doc["channel_id"]):
        raise ValueError("channel")
    values = {
        "LINE_ROLE_MENU_FEATURES_ENABLED": "true" if mode == "global" else "false",
        "LINE_ROLE_MENU_TEST_ENABLED": "true" if mode == "bounded" else "false",
        "LINE_STAFF_MENU_ENABLED": "false",
        "LINE_ROLE_MENU_BOT_SHA256": manifest.bot_fingerprint,
        "LINE_ROLE_MENU_TEST_CHANNEL_ID": "",
        "LINE_ROLE_MENU_TEST_USER_SHA256": "",
        "LINE_ROLE_MENU_TEST_EXPIRES_AT": "",
    }
    if "ai" in doc:
        ai = doc["ai"]
        if (
            not isinstance(ai, dict)
            or set(ai) != {"celery_ai_enabled", "gemini_model_name"}
            or type(ai["celery_ai_enabled"]) is not bool
            or not isinstance(ai["gemini_model_name"], str)
            or not re.fullmatch(r"gemini-[a-z0-9.-]{1,80}", ai["gemini_model_name"])
        ):
            raise ValueError("ai_configuration")
        values["CELERY_AI_ENABLED"] = str(ai["celery_ai_enabled"]).lower()
        values["GEMINI_MODEL_NAME"] = ai["gemini_model_name"]
    if mode == "bounded":
        hashes = doc["user_sha256"]
        if (
            not isinstance(hashes, list)
            or not 1 <= len(hashes) <= 10
            or any(not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes)
            or len(set(hashes)) != len(hashes)
        ):
            raise ValueError("scope")
        expires = datetime.fromisoformat(doc["expires_at"])
        now = datetime.now(UTC)
        if expires.tzinfo is None or not now < expires <= now + timedelta(days=7):
            raise ValueError("expiry")
        values.update(
            LINE_ROLE_MENU_TEST_CHANNEL_ID=doc["channel_id"],
            LINE_ROLE_MENU_TEST_USER_SHA256=",".join(sorted(hashes)),
            LINE_ROLE_MENU_TEST_EXPIRES_AT=expires.astimezone(UTC).isoformat(),
        )
    if mode == "global":
        for key in ("report_path", "resources_path"):
            path = Path(doc[key])
            if production and not re.fullmatch(
                r"/var/lib/strayhub/line-rollout/evidence/[0-9a-f]{64}\.json", str(path)
            ):
                raise ValueError("evidence path")
            _safe_file(path, production=production)
        raw = Path(doc["report_path"]).read_bytes()
        report = json.loads(raw, object_pairs_hook=unique)
        # Full identity, resources, human PASS and approval validation is performed
        # by canonical preflight in the exact API image before accepting this config.
        if (
            report.get("schema_version") != 2
            or report.get("approval", {}).get("status") != "approved"
        ):
            raise ValueError("approval")
        values.update(
            LINE_ROLE_MENU_REPORT_PATH=doc["report_path"],
            LINE_ROLE_MENU_REPORT_SHA256=hashlib.sha256(raw).hexdigest(),
            LINE_ROLE_MENU_RESOURCES_PATH=doc["resources_path"],
            LINE_ROLE_MENU_RELEASE_MANIFEST="/opt/strayhub/current/release-manifest.json",
        )
    return values
