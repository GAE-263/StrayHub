"""Read-only normal demo inventory, with optional actual photo-byte verification."""

import argparse
import asyncio
import hashlib
import json

from scripts.local_demo import DEMO_SHELTERS, guard
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.infrastructure.storage.ports import ObjectScope
from services.api.app.persistence.database.engine import session_factory
from services.api.app.persistence.database.scope import set_organization_scope, set_platform_scope
from sqlalchemy import text


async def verify_shelter(code, *, photos=False):
    storage = MinioStorageAdapter() if photos else None
    async with session_factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION READ ONLY"))
        await set_platform_scope(session)
        org = (
            (
                await session.execute(
                    text("SELECT id,name,status FROM organizations WHERE code=:code"),
                    {"code": code},
                )
            )
            .mappings()
            .one_or_none()
        )
        if org is None:
            return {"animals": 0, "valid": False}
        await set_organization_scope(session, org["id"])
        rows = (
            (
                await session.execute(
                    text("""SELECT a.id, a.status, a.current_photo_key, m.checksum,
            m.status AS media_status, m.exif_removed,
            EXISTS(SELECT 1 FROM animal_qr_codes q WHERE q.animal_id=a.id
              AND q.organization_id=a.organization_id
              AND q.status='active' AND NOT q.revoked) AS qr,
            EXISTS(SELECT 1 FROM animal_external_sources x WHERE x.animal_id=a.id
              AND x.organization_id=a.organization_id AND x.source='MOA_ADOPTION_OPEN_DATA'
              AND x.source_shelter_id=:shelter AND x.source_snapshot->>'animal_kind'='狗') AS source
            FROM animals a LEFT JOIN media_assets m ON m.organization_id=a.organization_id
              AND m.object_key=a.current_photo_key WHERE a.organization_id=:oid"""),
                    {"oid": org["id"], "shelter": code.removeprefix("MOA-SHELTER-")},
                )
            )
            .mappings()
            .all()
        )
        valid = (
            org["status"] == "active" and bool(rows) and len(rows) == len({r["id"] for r in rows})
        )
        valid = valid and all(
            r["status"] == "active"
            and r["qr"]
            and r["checksum"]
            and r["media_status"] == "processed"
            and r["exif_removed"]
            and (code == "FURKIDS-ASIA" or r["source"])
            for r in rows
        )
        if code == "FURKIDS-ASIA":
            valid = valid and len(rows) == 5
        if photos and valid:
            for row in rows:
                try:
                    data = await storage.get(
                        scope=ObjectScope(org["id"]), key=row["current_photo_key"]
                    )
                    valid = valid and hashlib.sha256(data).hexdigest() == row["checksum"]
                except Exception:
                    valid = False
        return {"animals": len(rows), "valid": bool(valid), "photos_checked": photos}


async def verify(*, photos=False, expected_import_count=60):
    guard(storage=photos)
    async with session_factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION READ ONLY"))
        await set_platform_scope(session)
        codes = set((await session.scalars(text("SELECT code FROM organizations"))).all())
    if codes != set(DEMO_SHELTERS):
        raise RuntimeError(
            "unexpected_demo_organizations: use cleanup_legacy_demo_fixtures preview/--yes "
            "for legacy fixtures; unknown organizations are never deleted"
        )
    results = {code: await verify_shelter(code, photos=photos) for code in DEMO_SHELTERS}
    if not all(r["valid"] for r in results.values()):
        raise RuntimeError("demo_data_incomplete:" + json.dumps(results))
    for code, row in results.items():
        if code != "FURKIDS-ASIA" and row["animals"] != expected_import_count:
            row["warning"] = (
                f"Actual {row['animals']}; requested {expected_import_count}. "
                "Live source/previous imports can differ."
            )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(verify(photos=args.photos)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
