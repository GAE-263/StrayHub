"""Stage organization-specific volunteer access duration between migrations 0024/0025."""

from __future__ import annotations

import argparse
import asyncio
from uuid import UUID, uuid4

from services.api.app.config.settings import get_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("organization_id", type=UUID)
    parser.add_argument("duration_hours", type=int)
    parser.add_argument("--disable-applications", action="store_true")
    parser.add_argument("--reason", required=True)
    return parser


async def configure(
    organization_id: UUID,
    duration_hours: int,
    *,
    applications_enabled: bool,
    reason: str,
) -> None:
    normalized_reason = reason.strip()
    if duration_hours <= 0:
        raise ValueError("duration_hours must be positive")
    if not normalized_reason or len(normalized_reason) > 500:
        raise ValueError("reason must contain 1..500 characters")

    settings = get_settings()
    database_url = settings.database_migration_url or settings.database_url
    engine = create_async_engine(database_url)
    operation_id = uuid4()
    try:
        async with engine.begin() as connection:
            before = (
                (
                    await connection.execute(
                        text(
                            """SELECT applications_enabled, default_grant_duration_hours, version
                        FROM organization_volunteer_access_policies
                        WHERE organization_id = :organization_id
                        FOR UPDATE"""
                        ),
                        {"organization_id": organization_id},
                    )
                )
                .mappings()
                .one()
            )
            await connection.execute(
                text(
                    """UPDATE organization_volunteer_access_policies
                    SET applications_enabled = :applications_enabled,
                        default_grant_duration_hours = :duration_hours,
                        version = version + 1,
                        updated_at = now()
                    WHERE organization_id = :organization_id"""
                ),
                {
                    "organization_id": organization_id,
                    "applications_enabled": applications_enabled,
                    "duration_hours": duration_hours,
                },
            )
            await connection.execute(
                text(
                    """INSERT INTO audit_records (
                      id, organization_id, actor_user_id, actor_type, actor_reference,
                      operation_id, action, resource_type, resource_id, source_channel,
                      before_data, after_data, reason, result, created_at
                    ) VALUES (
                      :id, :organization_id, NULL, 'system', 'SYSTEM_MIGRATION',
                      :operation_id, 'volunteer_access_policy.migration_configured',
                      'organization_volunteer_access_policy', :organization_id, 'migration',
                      CAST(:before_data AS json), CAST(:after_data AS json),
                      :reason, 'success', now()
                    )"""
                ),
                {
                    "id": uuid4(),
                    "organization_id": organization_id,
                    "operation_id": operation_id,
                    "before_data": (
                        '{"applications_enabled": '
                        f"{str(before['applications_enabled']).lower()}, "
                        '"default_grant_duration_hours": '
                        f"{before['default_grant_duration_hours']}, "
                        f'"version": {before["version"]}}}'
                    ),
                    "after_data": (
                        '{"applications_enabled": '
                        f"{str(applications_enabled).lower()}, "
                        f'"default_grant_duration_hours": {duration_hours}, '
                        f'"version": {before["version"] + 1}}}'
                    ),
                    "reason": normalized_reason,
                },
            )
    finally:
        await engine.dispose()


def main() -> None:
    args = _parser().parse_args()
    asyncio.run(
        configure(
            args.organization_id,
            args.duration_hours,
            applications_enabled=not args.disable_applications,
            reason=args.reason,
        )
    )


if __name__ == "__main__":
    main()
