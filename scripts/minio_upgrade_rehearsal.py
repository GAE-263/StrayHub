"""Synthetic-data helper for rehearsing a MinIO server upgrade (see
docs/deployment/minio-upgrade-runbook.md).

It drives the app's real ``MinioStorageAdapter`` against a *rehearsal* MinIO and records
size / SHA-256 / ETag / Content-Type / user metadata for every object, so two states (before and
after an upgrade or rollback) can be compared exactly. Never point it at production: it writes
synthetic objects, so use only a disposable endpoint and bucket.

Environment: REHEARSAL_ENDPOINT, REHEARSAL_ACCESS_KEY, REHEARSAL_SECRET_KEY, REHEARSAL_BUCKET.

    uv run python -m scripts.minio_upgrade_rehearsal seed
    uv run python -m scripts.minio_upgrade_rehearsal snapshot before.json
    uv run python -m scripts.minio_upgrade_rehearsal compare before.json after.json
    uv run python -m scripts.minio_upgrade_rehearsal probe
    uv run python -m scripts.minio_upgrade_rehearsal after   # writes post-cutover objects
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import boto3
from botocore.exceptions import ClientError
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.infrastructure.storage.ports import ObjectMetadata, ObjectScope

ORGS = [
    UUID("11111111-1111-4111-8111-111111111111"),
    UUID("22222222-2222-4222-8222-222222222222"),
]
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _setting(name: str) -> str:
    try:
        return os.environ[f"REHEARSAL_{name}"]
    except KeyError:
        raise SystemExit(f"REHEARSAL_{name} is required") from None


def _endpoint() -> str:
    endpoint = _setting("ENDPOINT")
    if urlsplit(endpoint).hostname not in LOOPBACK_HOSTS:
        raise SystemExit("REHEARSAL_ENDPOINT must be a loopback address (synthetic data only)")
    return endpoint


def _client():
    return boto3.client(
        "s3",
        endpoint_url=_endpoint(),
        aws_access_key_id=_setting("ACCESS_KEY"),
        aws_secret_access_key=_setting("SECRET_KEY"),
        region_name="us-east-1",
    )


def _adapter() -> MinioStorageAdapter:
    return MinioStorageAdapter(client=_client(), bucket=_setting("BUCKET"))


def _metadata(data: bytes, content_type: str) -> ObjectMetadata:
    return ObjectMetadata(
        content_type=content_type,
        size=len(data),
        checksum=hashlib.sha256(data).hexdigest(),
        exif_removed=True,
        created_at=datetime.now(timezone.utc),
    )


def _synthetic_keys(rng: random.Random) -> list[tuple[str, int, str]]:
    keys: list[tuple[str, int, str]] = []
    for _ in range(10):
        keys.append(
            (
                f"growth-diary/{rng.getrandbits(64):016x}/{rng.getrandbits(64):016x}.media",
                rng.randint(20_000, 300_000),
                "image/webp",
            )
        )
    for i in range(5):
        keys.append(
            (
                f"care-reports/{rng.getrandbits(64):016x}/photo-{i}.webp",
                rng.randint(5_000, 200_000),
                "image/webp",
            )
        )
        keys.append(
            (
                f"animals/{rng.getrandbits(64):016x}/profile.webp",
                rng.randint(5_000, 200_000),
                "image/webp",
            )
        )
    deep = "/".join(f"lvl{i}" for i in range(12))
    # MinIO rejects a single path segment over 255 bytes (S3 allows 1024 for the whole key).
    long_key = "/".join(["k" * 200] * 4)
    keys += [
        ("動物/小福 的照片 #1.webp", 12_345, "image/webp"),
        ("special/a+b c%20d&e=f.webp", 2_048, "image/webp"),
        (f"deep/{deep}/leaf.bin", 4_096, "application/octet-stream"),
        (f"long/{long_key}/end.webp", 1_024, "image/webp"),
        ("empty/zero-byte.bin", 0, "application/octet-stream"),
        ("big/six-megabytes.bin", 6 * 1024 * 1024, "application/octet-stream"),
    ]
    return keys


async def seed() -> None:
    adapter = _adapter()
    await adapter.ensure_bucket()
    rng = random.Random(20261002)
    count = 0
    for org in ORGS:
        scope = ObjectScope(organization_id=org)
        for key, size, content_type in _synthetic_keys(rng):
            data = rng.randbytes(size)
            await adapter.put(
                scope=scope, key=key, data=data, metadata=_metadata(data, content_type)
            )
            count += 1
    print(f"seeded {count} objects across {len(ORGS)} organizations")


def snapshot(out: str) -> None:
    client, bucket, endpoint = _client(), _setting("BUCKET"), _endpoint()
    objects: dict[str, dict] = {}
    token = None
    while True:
        kwargs = {"Bucket": bucket}
        if token:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        for item in page.get("Contents", []):
            got = client.get_object(Bucket=bucket, Key=item["Key"])
            body = got["Body"].read()
            objects[item["Key"]] = {
                "size": len(body),
                "listed_size": item["Size"],
                "sha256": hashlib.sha256(body).hexdigest(),
                "etag": item["ETag"],
                "content_type": got.get("ContentType"),
                "metadata": got.get("Metadata", {}),
            }
        if not page.get("IsTruncated"):
            break
        token = page["NextContinuationToken"]
    client.head_bucket(Bucket=bucket)
    extra: dict[str, str] = {}
    try:
        client.get_bucket_policy(Bucket=bucket)
        extra["bucket_policy"] = "PRESENT"
    except ClientError as exc:
        extra["bucket_policy"] = exc.response["Error"]["Code"]
    if objects:
        request = urllib.request.Request(f"{endpoint}/{bucket}/{next(iter(objects))}")
        try:
            urllib.request.urlopen(request, timeout=10)
            extra["anonymous_get"] = "ALLOWED"
        except urllib.error.HTTPError as exc:
            extra["anonymous_get"] = f"HTTP {exc.code}"
    Path(out).write_text(
        json.dumps(
            {"objects": objects, "extra": extra}, indent=1, sort_keys=True, ensure_ascii=False
        )
    )
    total = sum(o["size"] for o in objects.values())
    print(f"snapshot {out}: {len(objects)} objects, {total} bytes, {extra}")


def compare(a_path: str, b_path: str, allow_extra_in_b: bool = False) -> int:
    a, b = json.loads(Path(a_path).read_text()), json.loads(Path(b_path).read_text())
    a_objects, b_objects = a["objects"], b["objects"]
    problems = []
    for key in sorted(set(a_objects) | set(b_objects)):
        if key not in b_objects:
            problems.append(f"MISSING in B: {key[:70]}")
        elif key not in a_objects:
            if not allow_extra_in_b:
                problems.append(f"EXTRA in B: {key[:70]}")
        elif a_objects[key] != b_objects[key]:
            changed = [f for f in a_objects[key] if a_objects[key][f] != b_objects[key].get(f)]
            problems.append(f"DIFF {changed}: {key[:70]}")
    if a["extra"] != b["extra"]:
        problems.append(f"bucket-level differs: {a['extra']} vs {b['extra']}")
    if problems:
        print("COMPARE FAIL")
        for problem in problems:
            print(" ", problem)
        return 1
    print(
        f"COMPARE OK: {len(a_objects)} objects identical "
        "(size, sha256, etag, content-type, user metadata); bucket-level identical"
    )
    return 0


async def probe() -> int:
    adapter, ok = _adapter(), True
    scope = ObjectScope(organization_id=ORGS[0])
    data = os.urandom(50_000)
    key = "probe/new-object.webp"
    await adapter.put(scope=scope, key=key, data=data, metadata=_metadata(data, "image/webp"))
    got, content_type = await adapter.get_with_content_type(scope=scope, key=key)
    ok &= got == data and content_type == "image/webp"
    url = await adapter.signed_url(scope=scope, key=key, expires_seconds=60)
    ok &= urllib.request.urlopen(url, timeout=10).read() == data
    await adapter.delete(scope=scope, key=key)
    try:
        await adapter.get(scope=scope, key=key)
        ok = False
    except ClientError as exc:
        ok &= exc.response["Error"]["Code"] in {"NoSuchKey", "404"}
    print("PROBE", "OK (put/get/content-type/presigned-url/delete/missing-key)" if ok else "FAIL")
    return 0 if ok else 1


async def after_cutover() -> None:
    adapter = _adapter()
    scope = ObjectScope(organization_id=ORGS[0])
    for i in range(5):
        data = os.urandom(10_000 + i)
        await adapter.put(
            scope=scope,
            key=f"after-cutover/new-{i}.webp",
            data=data,
            metadata=_metadata(data, "image/webp"),
        )
    print("wrote 5 post-cutover objects")


def main(argv: list[str]) -> int:
    commands = "seed | snapshot OUT | compare A B [--allow-extra] | probe | after"
    if not argv:
        raise SystemExit(f"usage: {commands}")
    command = argv[0]
    if command == "seed":
        asyncio.run(seed())
    elif command == "snapshot" and len(argv) == 2:
        snapshot(argv[1])
    elif command == "compare" and len(argv) >= 3:
        return compare(argv[1], argv[2], "--allow-extra" in argv)
    elif command == "probe":
        return asyncio.run(probe())
    elif command == "after":
        asyncio.run(after_cutover())
    else:
        raise SystemExit(f"usage: {commands}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
