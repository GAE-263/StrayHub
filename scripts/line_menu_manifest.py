"""Authoritative validation for immutable LINE Rich Menu publication manifests."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

GIT_SHA = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
RICH_MENU_ID = re.compile(r"richmenu-[A-Za-z0-9-]+")
BOT_BASIC_ID = re.compile(r"@[A-Za-z0-9._-]+")
REQUIRED_ROLES = ("default", "volunteer", "adoption_hub")
KNOWN_ROLES = frozenset((*REQUIRED_ROLES, "adopter", "staff"))


class MenuManifestError(ValueError):
    """A publication manifest cannot be trusted for runtime configuration."""


@dataclass(frozen=True)
class VerifiedMenuManifest:
    git_sha: str
    bot_basic_id: str
    bot_fingerprint: str
    manifest_sha256: str
    menus: dict[str, dict[str, str]]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MenuManifestError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _exact_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise MenuManifestError(f"{label} contains unknown fields: {', '.join(sorted(unknown))}")


def load_publication_manifest(
    path: Path,
    *,
    expected_git_sha: str,
    expected_bot_basic_id: str,
) -> VerifiedMenuManifest:
    """Load the existing publication schema and require three verified resources.

    The publication API does not expose a Messaging Channel ID, so the existing
    authoritative contract binds the Bot by basic ID and hashed Bot user ID.
    """

    if not GIT_SHA.fullmatch(expected_git_sha):
        raise MenuManifestError("expected manifest Git SHA must be full lowercase SHA-1")
    if not BOT_BASIC_ID.fullmatch(expected_bot_basic_id):
        raise MenuManifestError("expected Bot basic ID is invalid")
    try:
        raw = path.read_bytes()
        data = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except MenuManifestError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MenuManifestError("unable to parse publication manifest") from exc
    if not isinstance(data, dict):
        raise MenuManifestError("publication manifest must be a JSON object")
    _exact_keys(data, {"schema", "git_sha", "bot", "resources", "updated_at"}, "manifest")
    if data.get("schema") != 1:
        raise MenuManifestError("unsupported publication manifest schema")
    git_sha = data.get("git_sha")
    if git_sha != expected_git_sha or not isinstance(git_sha, str):
        raise MenuManifestError("publication manifest Git SHA mismatch")

    bot = data.get("bot")
    if not isinstance(bot, dict):
        raise MenuManifestError("publication manifest Bot identity is missing")
    _exact_keys(bot, {"basic_id", "bot_fp"}, "manifest.bot")
    if bot.get("basic_id") != expected_bot_basic_id:
        raise MenuManifestError("publication manifest Bot identity mismatch")
    bot_fp = bot.get("bot_fp")
    if not isinstance(bot_fp, str) or not SHA256.fullmatch(bot_fp):
        raise MenuManifestError("publication manifest Bot fingerprint is invalid")

    resources = data.get("resources")
    if not isinstance(resources, dict):
        raise MenuManifestError("publication manifest resources must be an object")
    by_role: dict[str, dict[str, str]] = {}
    for fingerprint, record in resources.items():
        if not isinstance(fingerprint, str) or not SHA256.fullmatch(fingerprint):
            raise MenuManifestError("publication resource fingerprint is invalid")
        if not isinstance(record, dict):
            raise MenuManifestError("publication resource record must be an object")
        _exact_keys(
            record,
            {
                "role",
                "definition_sha256",
                "image_sha256",
                "stage",
                "verified",
                "id",
                "history",
            },
            "manifest resource",
        )
        role = record.get("role")
        if role not in KNOWN_ROLES:
            raise MenuManifestError("publication resource role is invalid")
        if role in by_role:
            raise MenuManifestError(f"publication manifest has duplicate role: {role}")
        resource_id = record.get("id")
        definition_hash = record.get("definition_sha256")
        image_hash = record.get("image_sha256")
        if record.get("stage") != "ready" or record.get("verified") is not True:
            if role in REQUIRED_ROLES:
                raise MenuManifestError(f"required publication resource is not ready: {role}")
            continue
        if not isinstance(resource_id, str) or not RICH_MENU_ID.fullmatch(resource_id):
            raise MenuManifestError(f"publication resource ID is invalid: {role}")
        if not isinstance(definition_hash, str) or not SHA256.fullmatch(definition_hash):
            raise MenuManifestError(f"publication definition hash is invalid: {role}")
        if not isinstance(image_hash, str) or not SHA256.fullmatch(image_hash):
            raise MenuManifestError(f"publication image hash is invalid: {role}")
        by_role[role] = {
            "id": resource_id,
            "definition_sha256": definition_hash,
            "image_sha256": image_hash,
        }

    missing = set(REQUIRED_ROLES) - set(by_role)
    if missing:
        raise MenuManifestError(
            f"publication manifest is missing ready roles: {', '.join(sorted(missing))}"
        )
    required_ids = [by_role[role]["id"] for role in REQUIRED_ROLES]
    if len(required_ids) != len(set(required_ids)):
        raise MenuManifestError("required publication roles must use distinct resources")
    return VerifiedMenuManifest(
        git_sha=git_sha,
        bot_basic_id=expected_bot_basic_id,
        bot_fingerprint=bot_fp,
        manifest_sha256=sha256(raw).hexdigest(),
        menus={role: by_role[role] for role in REQUIRED_ROLES},
    )
