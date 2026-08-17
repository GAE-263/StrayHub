"""Measure the complete care-agenda read path against a deterministic seed manifest."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import sys
from collections.abc import Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

from services.api.app.api.dependencies import RequestContext
from services.api.app.application.care_agenda_service import CareAgendaService
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope, set_platform_scope
from services.api.app.persistence.models.identity import OrganizationMembership, User
from sqlalchemy import event, select

BUCKETS = ("today_pending", "overdue", "today_resolved", "next_seven_days")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--page-size", type=int, default=1000)
    return parser


def percentile(values: Sequence[float], percentile_value: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("至少需要一筆量測資料")
    rank = max(1, int(len(ordered) * percentile_value + 0.999999))
    return ordered[min(rank, len(ordered)) - 1]


def expected_buckets(manifest: dict[str, Any]) -> dict[str, set[str]]:
    buckets = manifest.get("buckets")
    if not isinstance(buckets, dict):
        raise ValueError("manifest 缺少 buckets")
    result: dict[str, set[str]] = {}
    for name in BUCKETS:
        bucket = buckets.get(name)
        if not isinstance(bucket, dict) or not isinstance(bucket.get("occurrence_ids"), list):
            raise ValueError(f"manifest bucket 格式錯誤：{name}")
        occurrence_ids = {str(item) for item in bucket["occurrence_ids"]}
        if bucket.get("total") != len(occurrence_ids):
            raise ValueError(f"manifest bucket total 不一致：{name}")
        result[name] = occurrence_ids
    return result


async def load_context(organization_id: UUID) -> RequestContext:
    async with session_factory() as session:
        async with session.begin():
            await set_platform_scope(session)
            row = (
                await session.execute(
                    select(User, OrganizationMembership)
                    .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
                    .where(
                        OrganizationMembership.organization_id == organization_id,
                        OrganizationMembership.role == "SHELTER_ADMIN",
                        OrganizationMembership.status == "active",
                    )
                    .order_by(OrganizationMembership.created_at)
                    .limit(1)
                )
            ).one_or_none()
    if row is None:
        raise RuntimeError("找不到可量測的 SHELTER_ADMIN membership")
    user, membership = row
    return RequestContext(
        user_id=user.id,
        organization_id=organization_id,
        membership_id=membership.id,
        role=membership.role,
    )


async def measure_once(
    *,
    context: RequestContext,
    target_day: date,
    page_size: int,
    query_tracker: dict[str, int | bool],
) -> tuple[float, int, dict[str, set[str]], dict[str, int], int]:
    query_tracker["count"] = 0
    query_tracker["active"] = True
    started = perf_counter()
    try:
        async with session_factory() as session:
            async with session.begin():
                await set_organization_scope(session, context.organization_id)  # type: ignore[arg-type]
                response = await CareAgendaService(session, context).build(
                    target_day=target_day,
                    page_size=page_size,
                )
                payload = json.dumps(response, ensure_ascii=False, sort_keys=True)
        elapsed_ms = (perf_counter() - started) * 1000
    finally:
        query_tracker["active"] = False

    actual: dict[str, set[str]] = {}
    totals: dict[str, int] = {}
    for name in BUCKETS:
        bucket = response[name]
        if not isinstance(bucket, dict):
            raise RuntimeError(f"Agenda bucket 格式錯誤：{name}")
        items = bucket["items"]
        if not isinstance(items, list):
            raise RuntimeError(f"Agenda items 格式錯誤：{name}")
        actual[name] = {str(item["occurrence_id"]) for item in items}
        totals[name] = int(bucket["total_count"])
    return elapsed_ms, int(query_tracker["count"]), actual, totals, len(payload.encode())


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.rounds < 1 or args.warmups < 0 or args.samples < 1 or args.page_size < 1:
        raise ValueError("rounds/samples/page-size 必須為正數，warmups 不得為負數")
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    expected = expected_buckets(manifest)
    organization_id = UUID(str(manifest["organization_id"]))
    target_day = date.fromisoformat(str(manifest["generated_for_local_date"]))
    context = await load_context(organization_id)
    query_tracker: dict[str, int | bool] = {"active": False, "count": 0}

    def count_query(*_: object, **__: object) -> None:
        if query_tracker["active"]:
            query_tracker["count"] = int(query_tracker["count"]) + 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_query)
    round_results: list[dict[str, Any]] = []
    total_missing: set[str] = set()
    total_unexpected: set[str] = set()
    try:
        for round_number in range(1, args.rounds + 1):
            for _ in range(args.warmups):
                await measure_once(
                    context=context,
                    target_day=target_day,
                    page_size=args.page_size,
                    query_tracker=query_tracker,
                )
            durations: list[float] = []
            query_counts: list[int] = []
            payload_sizes: list[int] = []
            round_missing: set[str] = set()
            round_unexpected: set[str] = set()
            observed_totals: dict[str, int] = {}
            for _ in range(args.samples):
                elapsed_ms, query_count, actual, totals, payload_size = await measure_once(
                    context=context,
                    target_day=target_day,
                    page_size=args.page_size,
                    query_tracker=query_tracker,
                )
                durations.append(elapsed_ms)
                query_counts.append(query_count)
                payload_sizes.append(payload_size)
                observed_totals = totals
                for name in BUCKETS:
                    round_missing.update(expected[name] - actual[name])
                    round_unexpected.update(actual[name] - expected[name])
            total_missing.update(round_missing)
            total_unexpected.update(round_unexpected)
            result = {
                "round": round_number,
                "warmups": args.warmups,
                "samples": args.samples,
                "latency_ms": {
                    "p50": round(percentile(durations, 0.50), 3),
                    "p95": round(percentile(durations, 0.95), 3),
                    "max": round(max(durations), 3),
                },
                "sql_queries": {
                    "min": min(query_counts),
                    "max": max(query_counts),
                },
                "serialized_bytes": {
                    "min": min(payload_sizes),
                    "max": max(payload_sizes),
                },
                "bucket_totals": observed_totals,
                "missing_occurrence_ids": sorted(round_missing),
                "unexpected_occurrence_ids": sorted(round_unexpected),
                "classification_pass_rate": 1.0
                if not round_missing and not round_unexpected
                else 0.0,
            }
            round_results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_query)
        await engine.dispose()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": {
            "rounds": args.rounds,
            "warmups_per_round": args.warmups,
            "samples_per_round": args.samples,
            "page_size": args.page_size,
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
        },
        "source": {
            "manifest": str(args.manifest.resolve()),
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "organization_id": str(organization_id),
            "target_day": target_day.isoformat(),
            "expected_occurrence_count": sum(len(items) for items in expected.values()),
            "expected_bucket_totals": {name: len(expected[name]) for name in BUCKETS},
        },
        "rounds": round_results,
        "overall": {
            "missing_occurrence_ids": sorted(total_missing),
            "unexpected_occurrence_ids": sorted(total_unexpected),
            "classification_pass_rate": 1.0 if not total_missing and not total_unexpected else 0.0,
        },
    }


def main() -> int:
    args = build_parser().parse_args()
    result = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if result["overall"]["classification_pass_rate"] != 1.0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
