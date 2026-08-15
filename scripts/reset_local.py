"""Safely remove only the deterministic local MVP data set."""

from __future__ import annotations

import argparse
import asyncio

from services.api.app.persistence.database.engine import session_factory
from sqlalchemy import text

ORGANIZATION_CODES = ("ORG-A", "ORG-B", "ORG-DISABLED")


async def reset() -> int:
    async with session_factory() as session:
        async with session.begin():
            organization_ids = [
                row[0]
                for row in (
                    await session.execute(
                        text("SELECT id FROM organizations WHERE code = ANY(:codes)"),
                        {"codes": list(ORGANIZATION_CODES)},
                    )
                ).all()
            ]
            if not organization_ids:
                return 0
            params = {"organization_ids": organization_ids}
            await session.execute(
                text(
                    """
                    DELETE FROM care_report_media
                    WHERE report_id IN (
                        SELECT id FROM care_reports WHERE organization_id = ANY(:organization_ids)
                    )
                    """
                ),
                params,
            )
            await session.execute(
                text(
                    "DELETE FROM draft_media_assets WHERE draft_id IN "
                    "(SELECT id FROM care_report_drafts "
                    "WHERE organization_id = ANY(:organization_ids))"
                ),
                params,
            )
            for table in (
                "volunteer_notification_retry_batch_items",
                "volunteer_notification_retry_batches",
                "volunteer_decision_batch_items",
                "volunteer_decision_batches",
                "volunteer_notification_deliveries",
                "volunteer_access_grants",
                "volunteer_applications",
                "shelter_volunteer_entry_references",
                "organization_volunteer_access_policies",
                "care_report_corrections",
                "report_idempotency_keys",
                "ai_call_logs",
                "ai_observations",
                "ai_processing_jobs",
                "care_reports",
                "care_report_drafts",
                "media_assets",
                "daily_reportable_scopes",
                "animal_qr_codes",
                "animals",
                "shelter_areas",
                "audit_records",
                "webhook_sessions",
            ):
                await session.execute(
                    text(f"DELETE FROM {table} WHERE organization_id = ANY(:organization_ids)"),
                    params,
                )
            await session.execute(
                text(
                    "DELETE FROM refresh_token_records WHERE session_id IN ("
                    "SELECT id FROM session_records WHERE "
                    "active_organization_id = ANY(:organization_ids) "
                    "OR user_id IN (SELECT id FROM users WHERE username LIKE 'local-%'))"
                ),
                params,
            )
            await session.execute(
                text(
                    "DELETE FROM session_records "
                    "WHERE active_organization_id = ANY(:organization_ids) "
                    "OR user_id IN (SELECT id FROM users WHERE username LIKE 'local-%')"
                ),
                params,
            )
            await session.execute(
                text(
                    "DELETE FROM line_user_bindings WHERE user_id IN "
                    "(SELECT id FROM users WHERE username LIKE 'local-%')"
                )
            )
            await session.execute(
                text(
                    "DELETE FROM organization_memberships "
                    "WHERE organization_id = ANY(:organization_ids)"
                ),
                params,
            )
            await session.execute(
                text(
                    "DELETE FROM users WHERE username LIKE 'local-%' "
                    "AND id NOT IN (SELECT user_id FROM organization_memberships)"
                )
            )
            deleted = await session.execute(
                text("DELETE FROM organizations WHERE id = ANY(:organization_ids)"), params
            )
            return deleted.rowcount or 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="確認只刪除 ORG-A／ORG-B 及 username 為 local-* 的本機資料",
    )
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("Reset 僅允許使用 --yes 明確確認本機 ORG-A／ORG-B 資料")
    print(f"已刪除 {asyncio.run(reset())} 個本機 Organization")


if __name__ == "__main__":
    main()
