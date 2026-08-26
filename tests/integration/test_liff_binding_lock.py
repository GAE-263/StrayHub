import os
from uuid import uuid4

import asyncpg
import pytest


def database_url() -> str:
    return os.environ["STRAYHUB_TEST_DATABASE_URL"]


@pytest.mark.asyncio
async def test_line_binding_authorization_lock_blocks_concurrent_revocation() -> None:
    authorization_connection = await asyncpg.connect(database_url())
    writer_connection = await asyncpg.connect(database_url())
    user_id = uuid4()
    binding_id = uuid4()
    line_user_id = f"U-lock-{uuid4().hex}"
    try:
        await authorization_connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Binding lock user', 'active', now(), now())
            """,
            user_id,
            f"binding-lock-{user_id.hex}",
        )
        await authorization_connection.execute(
            """
            INSERT INTO line_user_bindings
              (id, line_user_id, user_id, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'active', now(), now())
            """,
            binding_id,
            line_user_id,
            user_id,
        )

        await authorization_connection.execute("BEGIN")
        locked = await authorization_connection.fetchrow(
            """
            SELECT id, status
            FROM line_user_bindings
            WHERE line_user_id = $1 AND status = 'active'
            FOR UPDATE
            """,
            line_user_id,
        )
        assert locked is not None

        await writer_connection.execute("BEGIN")
        await writer_connection.execute("SET LOCAL lock_timeout = '100ms'")
        with pytest.raises(asyncpg.exceptions.LockNotAvailableError):
            await writer_connection.execute(
                "UPDATE line_user_bindings SET status = 'revoked' WHERE id = $1",
                binding_id,
            )
        await writer_connection.execute("ROLLBACK")
        await authorization_connection.execute("ROLLBACK")

        await writer_connection.execute("BEGIN")
        await writer_connection.execute(
            "UPDATE line_user_bindings SET status = 'revoked' WHERE id = $1", binding_id
        )
        await writer_connection.execute("ROLLBACK")
    finally:
        await authorization_connection.execute(
            "DELETE FROM line_user_bindings WHERE id = $1", binding_id
        )
        await authorization_connection.execute("DELETE FROM users WHERE id = $1", user_id)
        await authorization_connection.close()
        await writer_connection.close()
