import os
from datetime import timedelta
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.domain.volunteer_access import (
    ENTRY_REFERENCE_PURPOSE,
    digest_entry_reference,
)


def _database_url() -> str:
    return os.environ["STRAYHUB_TEST_DATABASE_URL"]


@pytest.mark.asyncio
async def test_real_postgres_entry_resolver_is_expiry_purpose_and_status_closed() -> None:
    connection = await asyncpg.connect(_database_url())
    organization_id = uuid4()
    organization_code = f"ENTRY-{organization_id.hex[:10]}"
    valid_raw = "valid-entry-" + uuid4().hex
    expired_raw = "expired-entry-" + uuid4().hex
    wrong_purpose_raw = "wrong-purpose-entry-" + uuid4().hex
    revoked_raw = "revoked-entry-" + uuid4().hex
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Entry shelter', $2, 'active', now(), now())
            """,
            organization_id,
            organization_code,
        )
        for raw_reference, purpose, status, expires_delta in (
            (valid_raw, ENTRY_REFERENCE_PURPOSE, "active", timedelta(days=7)),
            (expired_raw, ENTRY_REFERENCE_PURPOSE, "active", timedelta(seconds=-1)),
            (wrong_purpose_raw, "different_purpose", "active", timedelta(days=7)),
            (revoked_raw, ENTRY_REFERENCE_PURPOSE, "revoked", timedelta(days=7)),
        ):
            revoked = status == "revoked"
            await connection.execute(
                """
                INSERT INTO shelter_volunteer_entry_references
                  (id, organization_id, token_digest, purpose, status,
                   issued_by_actor_reference, issued_at, expires_at,
                   revoked_by_actor_reference, revoked_at, rotation_group_id,
                   created_at, updated_at)
                VALUES
                  ($1, $2, $3, $4, $5, 'TEST', now(), now() + $6,
                   $7, CASE WHEN $8::boolean THEN now() ELSE NULL END,
                   $9, now(), now())
                """,
                uuid4(),
                organization_id,
                digest_entry_reference(raw_reference),
                purpose,
                status,
                expires_delta,
                "TEST" if revoked else None,
                revoked,
                uuid4(),
            )

        await connection.execute("SET ROLE strayhub_runtime")

        valid = await connection.fetchrow(
            "SELECT * FROM resolve_volunteer_entry_reference($1, $2)",
            digest_entry_reference(valid_raw),
            ENTRY_REFERENCE_PURPOSE,
        )
        assert valid is not None
        assert valid["organization_id"] == organization_id
        assert valid["organization_code"] == organization_code
        assert valid["organization_name"] == "Entry shelter"

        for raw_reference in (expired_raw, wrong_purpose_raw, revoked_raw):
            assert (
                await connection.fetchrow(
                    "SELECT * FROM resolve_volunteer_entry_reference($1, $2)",
                    digest_entry_reference(raw_reference),
                    ENTRY_REFERENCE_PURPOSE,
                )
                is None
            )
        await connection.execute("ROLLBACK")
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_entry_resolver_holds_entry_and_organization_locks_until_transaction_end() -> None:
    resolver_connection = await asyncpg.connect(_database_url())
    writer_connection = await asyncpg.connect(_database_url())
    organization_id = uuid4()
    entry_id = uuid4()
    raw_reference = "locked-entry-" + uuid4().hex
    try:
        await resolver_connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Locked entry shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"LOCK-{organization_id.hex[:10]}",
        )
        await resolver_connection.execute(
            """
            INSERT INTO shelter_volunteer_entry_references
              (id, organization_id, token_digest, purpose, status,
               issued_by_actor_reference, issued_at, expires_at, rotation_group_id,
               created_at, updated_at)
            VALUES
              ($1, $2, $3, $4, 'active', 'TEST', now(), now() + interval '7 days',
               $5, now(), now())
            """,
            entry_id,
            organization_id,
            digest_entry_reference(raw_reference),
            ENTRY_REFERENCE_PURPOSE,
            uuid4(),
        )

        await resolver_connection.execute("BEGIN")
        await resolver_connection.execute("SET ROLE strayhub_runtime")
        resolved = await resolver_connection.fetchrow(
            "SELECT * FROM resolve_volunteer_entry_reference($1, $2)",
            digest_entry_reference(raw_reference),
            ENTRY_REFERENCE_PURPOSE,
        )
        assert resolved is not None

        for statement, value in (
            (
                "UPDATE shelter_volunteer_entry_references SET updated_at = now() WHERE id = $1",
                entry_id,
            ),
            ("UPDATE organizations SET updated_at = now() WHERE id = $1", organization_id),
        ):
            await writer_connection.execute("BEGIN")
            await writer_connection.execute("SET LOCAL lock_timeout = '100ms'")
            with pytest.raises(asyncpg.exceptions.LockNotAvailableError):
                await writer_connection.execute(statement, value)
            await writer_connection.execute("ROLLBACK")

        await resolver_connection.execute("ROLLBACK")

        await writer_connection.execute("BEGIN")
        await writer_connection.execute(
            "UPDATE organizations SET updated_at = now() WHERE id = $1", organization_id
        )
        await writer_connection.execute("ROLLBACK")
    finally:
        await resolver_connection.execute("RESET ROLE")
        await resolver_connection.execute(
            "DELETE FROM shelter_volunteer_entry_references WHERE id = $1", entry_id
        )
        await resolver_connection.execute(
            "DELETE FROM organizations WHERE id = $1", organization_id
        )
        await resolver_connection.close()
        await writer_connection.close()


@pytest.mark.asyncio
async def test_user_authorization_lock_blocks_concurrent_disable() -> None:
    authorization_connection = await asyncpg.connect(_database_url())
    writer_connection = await asyncpg.connect(_database_url())
    user_id = uuid4()
    try:
        await authorization_connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Locked authorization user', 'active', now(), now())
            """,
            user_id,
            f"locked-user-{user_id.hex[:10]}",
        )
        await authorization_connection.execute("BEGIN")
        locked_user = await authorization_connection.fetchrow(
            "SELECT id, status FROM users WHERE id = $1 FOR UPDATE", user_id
        )
        assert locked_user is not None
        assert locked_user["status"] == "active"

        await writer_connection.execute("BEGIN")
        await writer_connection.execute("SET LOCAL lock_timeout = '100ms'")
        with pytest.raises(asyncpg.exceptions.LockNotAvailableError):
            await writer_connection.execute(
                "UPDATE users SET status = 'disabled', updated_at = now() WHERE id = $1",
                user_id,
            )
        await writer_connection.execute("ROLLBACK")
        await authorization_connection.execute("ROLLBACK")

        await writer_connection.execute("BEGIN")
        await writer_connection.execute(
            "UPDATE users SET status = 'disabled', updated_at = now() WHERE id = $1", user_id
        )
        await writer_connection.execute("ROLLBACK")
    finally:
        await authorization_connection.execute("DELETE FROM users WHERE id = $1", user_id)
        await authorization_connection.close()
        await writer_connection.close()
