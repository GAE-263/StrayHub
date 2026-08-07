import hashlib
import os
from uuid import uuid4

import asyncpg
import pytest


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:56432/strayhub",
    )


@pytest.mark.asyncio
async def test_qr_token_tampering_cross_org_and_revocation_are_not_resolvable() -> None:
    connection = await asyncpg.connect(_database_url())
    organization_a = uuid4()
    organization_b = uuid4()
    animal_a = uuid4()
    animal_b = uuid4()
    qr_a = uuid4()
    qr_b = uuid4()
    token_a = f"token-a-{uuid4().hex}"
    token_b = f"token-b-{uuid4().hex}"
    active_qr_sql = """
        SELECT animal_id
        FROM animal_qr_codes
        WHERE token_digest = $1 AND status = 'active' AND NOT revoked
    """
    try:
        await connection.execute("BEGIN")
        await connection.execute("SET ROLE strayhub_runtime")
        await connection.execute("SELECT set_config('app.platform_scope', 'true', true)")
        for organization_id, code in (
            (organization_a, f"QR-A-{organization_a.hex[:10]}"),
            (organization_b, f"QR-B-{organization_b.hex[:10]}"),
        ):
            await connection.execute(
                """
                INSERT INTO organizations (id, name, code, status, created_at, updated_at)
                VALUES ($1, $2, $3, 'active', now(), now())
                """,
                organization_id,
                code,
                code,
            )
        await connection.execute(
            """
            INSERT INTO animals (id, organization_id, name, status, created_at, updated_at)
            VALUES ($1, $2, 'A', 'active', now(), now()),
                   ($3, $4, 'B', 'active', now(), now())
            """,
            animal_a,
            organization_a,
            animal_b,
            organization_b,
        )
        await connection.execute(
            """
            INSERT INTO animal_qr_codes
                (id, organization_id, animal_id, token_digest, status, revoked,
                 created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'active', false, now(), now()),
                   ($5, $6, $7, $8, 'active', false, now(), now())
            """,
            qr_a,
            organization_a,
            animal_a,
            hashlib.sha256(token_a.encode()).hexdigest(),
            qr_b,
            organization_b,
            animal_b,
            hashlib.sha256(token_b.encode()).hexdigest(),
        )
        await connection.execute("SELECT set_config('app.platform_scope', 'false', true)")
        await connection.execute(
            "SELECT set_config('app.current_org_id', $1, true)", str(organization_a)
        )
        assert (
            await connection.fetchval(
                active_qr_sql,
                hashlib.sha256(token_a.encode()).hexdigest(),
            )
            == animal_a
        )
        assert (
            await connection.fetchval(
                active_qr_sql,
                hashlib.sha256(token_b.encode()).hexdigest(),
            )
            is None
        )
        assert (
            await connection.fetchval(
                active_qr_sql,
                hashlib.sha256(f"{token_a}-tampered".encode()).hexdigest(),
            )
            is None
        )
        await connection.execute(
            "UPDATE animal_qr_codes SET revoked = true, status = 'revoked' WHERE id = $1", qr_a
        )
        assert (
            await connection.fetchval(
                active_qr_sql,
                hashlib.sha256(token_a.encode()).hexdigest(),
            )
            is None
        )
    finally:
        await connection.execute("ROLLBACK")
        await connection.close()
