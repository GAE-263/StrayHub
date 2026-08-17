"""Issue, rotate, or revoke a shelter volunteer entry reference."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import secrets
from uuid import UUID, uuid4

from services.api.app.config.settings import get_settings
from services.api.app.domain.volunteer_access import ENTRY_REFERENCE_PURPOSE
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("organization_id", type=UUID)
    parser.add_argument("--actor-user-id", type=UUID)
    parser.add_argument("--actor-reference", default="SYSTEM_MIGRATION")
    parser.add_argument("--rotate-reference-id", type=UUID)
    parser.add_argument("--revoke-reference-id", type=UUID)
    return parser


def generate_reference() -> tuple[str, str]:
    raw_reference = secrets.token_urlsafe(32)
    return raw_reference, hashlib.sha256(raw_reference.encode()).hexdigest()


async def issue(
    organization_id: UUID,
    *,
    actor_user_id: UUID | None,
    actor_reference: str | None,
    rotate_reference_id: UUID | None = None,
    revoke_reference_id: UUID | None = None,
) -> tuple[UUID | None, str | None]:
    if (actor_user_id is None) == (actor_reference is None):
        raise ValueError("provide exactly one actor")
    if rotate_reference_id is not None and revoke_reference_id is not None:
        raise ValueError("rotate and revoke are mutually exclusive")

    settings = get_settings()
    database_url = settings.database_migration_url or settings.database_url
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            actor_values = {
                "actor_user_id": actor_user_id,
                "actor_reference": actor_reference,
                "organization_id": organization_id,
            }
            if revoke_reference_id is not None:
                result = await connection.execute(
                    text(
                        """UPDATE shelter_volunteer_entry_references
                        SET status = 'revoked', revoked_at = now(),
                            revoked_by_user_id = :actor_user_id,
                            revoked_by_actor_reference = :actor_reference,
                            updated_at = now()
                        WHERE id = :reference_id
                          AND organization_id = :organization_id
                          AND status = 'active'"""
                    ),
                    {**actor_values, "reference_id": revoke_reference_id},
                )
                if result.rowcount != 1:
                    raise ValueError("active reference not found")
                return revoke_reference_id, None

            rotation_group_id = uuid4()
            if rotate_reference_id is not None:
                existing = (
                    await connection.execute(
                        text(
                            """SELECT rotation_group_id
                            FROM shelter_volunteer_entry_references
                            WHERE id = :reference_id
                              AND organization_id = :organization_id
                              AND status = 'active'
                            FOR UPDATE"""
                        ),
                        {**actor_values, "reference_id": rotate_reference_id},
                    )
                ).scalar_one_or_none()
                if existing is None:
                    raise ValueError("active rotation source not found")
                rotation_group_id = existing

            raw_reference, token_digest = generate_reference()
            reference_id = uuid4()
            await connection.execute(
                text(
                    """INSERT INTO shelter_volunteer_entry_references (
                      id, organization_id, token_digest, purpose, status,
                      issued_by_user_id, issued_by_actor_reference, issued_at,
                      rotation_group_id, created_at, updated_at
                    ) VALUES (
                      :id, :organization_id, :token_digest, :purpose, 'active',
                      :actor_user_id, :actor_reference, now(),
                      :rotation_group_id, now(), now()
                    )"""
                ),
                {
                    **actor_values,
                    "id": reference_id,
                    "token_digest": token_digest,
                    "purpose": ENTRY_REFERENCE_PURPOSE,
                    "rotation_group_id": rotation_group_id,
                },
            )
            if rotate_reference_id is not None:
                await connection.execute(
                    text(
                        """UPDATE shelter_volunteer_entry_references
                        SET status = 'revoked', revoked_at = now(),
                            revoked_by_user_id = :actor_user_id,
                            revoked_by_actor_reference = :actor_reference,
                            updated_at = now()
                        WHERE id = :reference_id
                          AND organization_id = :organization_id"""
                    ),
                    {**actor_values, "reference_id": rotate_reference_id},
                )
            return reference_id, raw_reference
    finally:
        await engine.dispose()


def main() -> None:
    args = _parser().parse_args()
    actor_reference = None if args.actor_user_id else args.actor_reference
    reference_id, raw_reference = asyncio.run(
        issue(
            args.organization_id,
            actor_user_id=args.actor_user_id,
            actor_reference=actor_reference,
            rotate_reference_id=args.rotate_reference_id,
            revoke_reference_id=args.revoke_reference_id,
        )
    )
    # The raw reference is intentionally emitted exactly once and never persisted.
    print(json.dumps({"reference_id": str(reference_id), "raw_reference": raw_reference}))


if __name__ == "__main__":
    main()
