"""Synchronize one explicitly selected MOA shelter; never imports all shelters."""

from __future__ import annotations

import argparse
import asyncio
import json
import re

from services.api.app.application.moa_import_service import MoaImportService
from services.api.app.domain.moa_import import select_records
from services.api.app.infrastructure.moa_open_data import MoaOpenDataClient
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.persistence.database.engine import engine, session_factory
from sqlalchemy import text


async def run(args):
    stage = "source"
    try:
        async with MoaOpenDataClient() as client:
            batch = select_records(
                await client.fetch_records(), shelter=args.shelter, kind=args.kind, limit=args.limit
            )
            names = await client.fetch_names(batch)
            name_detail_requests = client.name_detail_requests
            photos = None if args.dry_run else await MoaImportService.download_photos(batch, client)
        stage = "database_or_storage"
        storage = MinioStorageAdapter()
        if not args.dry_run:
            await storage.ensure_bucket()
        async with session_factory() as session, session.begin():
            if args.dry_run:
                await session.execute(text("SET TRANSACTION READ ONLY"))
            summary = await MoaImportService(session, storage).run(
                batch=batch,
                shelter=args.shelter,
                limit=args.limit,
                photos=photos,
                names=names,
                name_detail_requests=name_detail_requests,
                dry_run=args.dry_run,
            )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2 if summary["errors"] else 0
    except Exception as exc:
        code = (
            str(exc)
            if isinstance(exc, ValueError) and re.fullmatch(r"[a-z][a-z0-9_]{1,80}", str(exc))
            else "import_failed"
        )
        print(json.dumps({"stage": stage, "error": code}, ensure_ascii=False))
        return 1
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shelter", required=True)
    parser.add_argument("--kind", choices=["dog"], default="dog")
    parser.add_argument("--limit", type=int, choices=range(1, 61), default=60, metavar="1..60")
    parser.add_argument("--dry-run", action="store_true")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
