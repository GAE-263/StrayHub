"""Resource-only publisher. No activation, deletion, user IDs or API settings.

One durable manifest per Bot; operators must serialize publishers across hosts.
An uncertain create intent is never automatically retried.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx


class PublicationError(RuntimeError):
    """Safe operator message; never include upstream bodies or credentials."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "resource_publication",
        candidate_ids: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.candidate_ids = candidate_ids


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def save_manifest(path: Path, state: dict) -> None:
    now = datetime.now(UTC).isoformat()
    state["updated_at"] = now
    for record in state["resources"].values():
        history = record.setdefault("history", [])
        if not history or history[-1]["stage"] != record["stage"]:
            history.append({"at": now, "stage": record["stage"]})
    fd, temporary = tempfile.mkstemp(prefix=".menu-manifest-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(state))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def menu_id(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"richmenu-[a-zA-Z0-9-]+", value):
        raise PublicationError("Invalid resource identifier; STOP")
    return value


class ResourcePublisher:
    _ALLOWED_REQUESTS = (
        ("GET", re.compile(r"info"), False),
        ("GET", re.compile(r"richmenu/list"), False),
        ("POST", re.compile(r"richmenu"), False),
        ("GET", re.compile(r"richmenu/richmenu-[A-Za-z0-9-]+"), False),
        ("GET", re.compile(r"richmenu/richmenu-[A-Za-z0-9-]+/content"), True),
        ("POST", re.compile(r"richmenu/richmenu-[A-Za-z0-9-]+/content"), True),
    )

    def __init__(self, client: httpx.AsyncClient):
        # Caller provides auth. Fixed hosts and no redirects prevent credential leakage.
        self.client = client
        self.outcomes: dict[str, str] = {}

    async def request(self, method: str, path: str, *, data_host=False, **kwargs):
        method = method.upper()
        if not any(
            method == allowed_method and data_host is allowed_data_host and pattern.fullmatch(path)
            for allowed_method, pattern, allowed_data_host in self._ALLOWED_REQUESTS
        ):
            raise PublicationError("LINE operation is outside the resource-publication allowlist")
        host = "api-data.line.me" if data_host else "api.line.me"
        try:
            response = await self.client.request(
                method, f"https://{host}/v2/bot/{path}", follow_redirects=False, **kwargs
            )
        except httpx.HTTPError:
            raise PublicationError(
                "LINE transport outcome unknown; resume with same manifest"
            ) from None
        if response.status_code == 404 and method == "GET" and path.endswith("/content"):
            return None
        if not 200 <= response.status_code < 300:
            raise PublicationError(f"LINE {method} HTTP {response.status_code}; STOP")
        return response

    async def publish(
        self,
        plan: dict,
        manifest: Path,
        expected_bot: str,
        git_sha: str,
        *,
        recovery_identity: dict | None = None,
    ) -> dict[str, str]:
        if not re.fullmatch(r"@[A-Za-z0-9._-]+", expected_bot):
            raise PublicationError("Explicit expected Bot basicId is required")
        if not re.fullmatch(r"[0-9a-f]{40}", git_sha):
            raise PublicationError("Explicit full lowercase publication Git SHA is required")
        # Persistent lock inode: never unlink, otherwise another process could bypass it.
        with manifest.with_suffix(manifest.suffix + ".lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise PublicationError("Manifest is locked; STOP") from None
            return await self._publish(
                plan, manifest, expected_bot, git_sha, recovery_identity=recovery_identity
            )

    async def _publish(
        self,
        plan: dict,
        manifest: Path,
        expected_bot: str,
        git_sha: str,
        *,
        recovery_identity: dict | None,
    ) -> dict[str, str]:
        bot = (await self.request("GET", "info")).json()
        if bot.get("basicId") != expected_bot or not bot.get("userId"):
            raise PublicationError("Bot identity mismatch; no writes permitted")
        identity = {"basic_id": expected_bot, "bot_fp": digest(bot["userId"].encode())}
        state: dict = (
            json.loads(manifest.read_text())
            if manifest.exists()
            else {
                "schema": 1,
                "git_sha": git_sha,
                "bot": identity,
                "resources": {},
                **({"recovery": recovery_identity} if recovery_identity else {}),
            }
        )
        if (
            state.get("schema") != 1
            or state.get("git_sha") != git_sha
            or state.get("bot") != identity
            or (recovery_identity is not None and state.get("recovery") != recovery_identity)
        ):
            raise PublicationError("Manifest Bot/schema/Git identity mismatch; STOP")

        for record in state["resources"].values():
            if isinstance(record, dict):
                record["verified"] = False
        save_manifest(manifest, state)

        # Validate every owned candidate before the first write. A later bad
        # candidate must not be discovered after an earlier image was uploaded.
        candidate_ids: set[str] = set()
        for fingerprint, record in state["resources"].items():
            rid = record.get("id")
            if not rid:
                continue
            rid = menu_id(rid)
            if rid in candidate_ids:
                raise PublicationError(
                    "Resume candidate is mapped more than once; STOP",
                    code="resume_source_invalid",
                    candidate_ids=(rid,),
                )
            candidate_ids.add(rid)
            item = next(
                (value for value in plan.values() if value.get("fingerprint") == fingerprint),
                None,
            )
            if item is None:
                raise PublicationError(
                    "Resume candidate has no matching local definition; STOP",
                    code="resume_candidate_mismatch",
                    candidate_ids=(rid,),
                )
            try:
                actual = (await self.request("GET", f"richmenu/{rid}")).json()
            except (PublicationError, ValueError):
                raise PublicationError(
                    "Resume candidate definition unavailable; STOP",
                    code="resume_candidate_mismatch",
                    candidate_ids=(rid,),
                ) from None
            if any(actual.get(key) != value for key, value in item["definition"].items()):
                raise PublicationError(
                    "Resume candidate definition mismatch; STOP",
                    code="resume_candidate_mismatch",
                    candidate_ids=(rid,),
                )
            try:
                image = await self.request("GET", f"richmenu/{rid}/content", data_host=True)
            except PublicationError:
                raise PublicationError(
                    "Resume candidate image readback unavailable; STOP",
                    code="resume_image_unreadable",
                    candidate_ids=(rid,),
                ) from None
            if image is not None and digest(image.content) != item["image_sha256"]:
                raise PublicationError(
                    "Resume candidate image mismatch; STOP",
                    code="resume_image_mismatch",
                    candidate_ids=(rid,),
                )

        # Classify every fresh role before creating any resource. This prevents
        # an earlier role from being written before a later orphan is noticed.
        listing = (await self.request("GET", "richmenu/list")).json()["richmenus"]
        for role, item in plan.items():
            record = state["resources"].get(item["fingerprint"], {})
            if record.get("id"):
                continue
            same_definition = [
                row
                for row in listing
                if all(row.get(key) == value for key, value in item["definition"].items())
            ]
            exact: list[str] = []
            incomplete: list[str] = []
            for candidate in same_definition:
                candidate_id = menu_id(candidate.get("richMenuId"))
                try:
                    image = await self.request(
                        "GET", f"richmenu/{candidate_id}/content", data_host=True
                    )
                except PublicationError:
                    raise PublicationError(
                        f"{role}: existing candidate image is unreadable; STOP",
                        code="unresolved_existing_candidate",
                        candidate_ids=(candidate_id,),
                    ) from None
                if image is None:
                    incomplete.append(candidate_id)
                elif digest(image.content) == item["image_sha256"]:
                    exact.append(candidate_id)
            if len(same_definition) > 1:
                raise PublicationError(
                    f"{role}: ambiguous matching resources; STOP",
                    code="ambiguous_candidates",
                    candidate_ids=tuple(sorted((*exact, *incomplete))),
                )
            if incomplete:
                raise PublicationError(
                    f"{role}: unresolved existing candidate(s) {','.join(incomplete)}; "
                    "trusted recovery progress is required; STOP",
                    code="unresolved_existing_candidate",
                    candidate_ids=tuple(incomplete),
                )
        result = {}
        self.outcomes = {}
        for role, item in plan.items():
            fingerprint = item["fingerprint"]
            entries = state["resources"]
            record = entries.setdefault(
                fingerprint,
                {
                    "role": role,
                    "definition_sha256": item["definition_sha256"],
                    "image_sha256": item["image_sha256"],
                    "stage": "planned",
                    "verified": False,
                },
            )
            if any(
                record.get(key) != value
                for key, value in {
                    "role": role,
                    "definition_sha256": item["definition_sha256"],
                    "image_sha256": item["image_sha256"],
                }.items()
            ):
                raise PublicationError(f"{role}: progress manifest fingerprint mismatch; STOP")
            wanted = item["definition"]
            record["verified"] = False
            save_manifest(manifest, state)
            rid = record.get("id")
            outcome = "reused"
            if not rid:
                listing = (await self.request("GET", "richmenu/list")).json()["richmenus"]
                definition_candidates = [
                    row for row in listing if all(row.get(k) == v for k, v in wanted.items())
                ]
                candidates = []
                incomplete_candidates = []
                for candidate in definition_candidates:
                    candidate_id = menu_id(candidate.get("richMenuId"))
                    try:
                        candidate_image = await self.request(
                            "GET", f"richmenu/{candidate_id}/content", data_host=True
                        )
                    except PublicationError:
                        raise PublicationError(
                            f"{role}: existing candidate image is unreadable; STOP",
                            code="unresolved_existing_candidate",
                            candidate_ids=(candidate_id,),
                        ) from None
                    if candidate_image is None:
                        incomplete_candidates.append(candidate_id)
                    elif digest(candidate_image.content) == item["image_sha256"]:
                        candidates.append(candidate_id)
                if (
                    len(definition_candidates) > 1
                    or len(candidates) > 1
                    or len(incomplete_candidates) > 1
                    or (candidates and incomplete_candidates)
                ):
                    raise PublicationError(
                        f"{role}: ambiguous matching resources; STOP",
                        code="ambiguous_candidates",
                        candidate_ids=tuple(sorted((*candidates, *incomplete_candidates))),
                    )
                if candidates:
                    rid = candidates[0]
                elif incomplete_candidates:
                    candidate_list = ",".join(sorted(incomplete_candidates))
                    raise PublicationError(
                        f"{role}: unresolved existing candidate(s) {candidate_list}; "
                        "trusted recovery progress is required; STOP",
                        code="unresolved_existing_candidate",
                        candidate_ids=tuple(incomplete_candidates),
                    )
                elif record["stage"] != "planned":
                    raise PublicationError(f"{role}: unresolved create intent; do not retry create")
                else:
                    record["stage"] = "create_intent"
                    save_manifest(manifest, state)  # before the potentially ambiguous POST
                    try:
                        response = await self.request("POST", "richmenu", json=wanted)
                        rid = menu_id(response.json().get("richMenuId"))
                        outcome = "created"
                    except (PublicationError, ValueError):
                        listing = (await self.request("GET", "richmenu/list")).json()["richmenus"]
                        matches = [
                            row
                            for row in listing
                            if all(row.get(k) == v for k, v in wanted.items())
                        ]
                        if len(matches) != 1:
                            raise PublicationError(
                                f"{role}: create outcome unknown; unresolved/ambiguous; STOP"
                            ) from None
                        rid = menu_id(matches[0]["richMenuId"])
                        outcome = "created"
                record["id"] = rid
                record["stage"] = "created"
                save_manifest(manifest, state)
            rid = menu_id(rid)
            record["stage"] = "verifying"
            save_manifest(manifest, state)
            actual = (await self.request("GET", f"richmenu/{rid}")).json()
            if any(actual.get(k) != v for k, v in wanted.items()):
                raise PublicationError(f"{role}: definition mismatch; STOP")
            image = await self.request("GET", f"richmenu/{rid}/content", data_host=True)
            if image is None:
                record["stage"] = "upload_pending"
                record["verified"] = False
                save_manifest(manifest, state)
                await self.request(
                    "POST",
                    f"richmenu/{rid}/content",
                    data_host=True,
                    content=item["image"],
                    headers={"Content-Type": item["content_type"]},
                )
                image = await self.request("GET", f"richmenu/{rid}/content", data_host=True)
            if image is None or digest(image.content) != item["image_sha256"]:
                record["verified"] = False
                record["stage"] = "verification_failed"
                save_manifest(manifest, state)
                raise PublicationError(f"{role}: image mismatch; STOP (no overwrite)")
            # Re-read definition after upload too; only both GETs can establish ready.
            actual = (await self.request("GET", f"richmenu/{rid}")).json()
            if any(actual.get(k) != v for k, v in wanted.items()):
                raise PublicationError(f"{role}: definition mismatch after upload; STOP")
            record.update(stage="ready", verified=True)
            save_manifest(manifest, state)
            result[role] = rid
            self.outcomes[role] = outcome
        return result
