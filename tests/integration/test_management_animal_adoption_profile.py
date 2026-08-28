from __future__ import annotations

import os
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.application.management_animal_service import ManagementAnimalService
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


async def _insert_fixtures(*, organization_id, animal_id, actor_user_id) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Adoption Profile Test Shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"PROFILE-{organization_id.hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Adoption Profile Test Staff', 'active', now(), now())
            """,
            actor_user_id,
            f"profile-staff-{actor_user_id.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO animals (id, organization_id, name, status, created_at, updated_at)
            VALUES ($1, $2, '待更新', 'active', now(), now())
            """,
            animal_id,
            organization_id,
        )
        await connection.execute("COMMIT")
    finally:
        await connection.close()


async def _cleanup(*, organization_id, actor_user_id) -> None:
    cleanup = await asyncpg.connect(_database_url())
    try:
        await cleanup.execute("BEGIN")
        await cleanup.execute(
            "DELETE FROM audit_records WHERE organization_id = $1", organization_id
        )
        await cleanup.execute("DELETE FROM animals WHERE organization_id = $1", organization_id)
        await cleanup.execute("DELETE FROM users WHERE id = $1", actor_user_id)
        await cleanup.execute("DELETE FROM organizations WHERE id = $1", organization_id)
        await cleanup.execute("COMMIT")
    finally:
        await cleanup.close()


@pytest.mark.asyncio
async def test_update_adoption_fields_persists_and_records_audit() -> None:
    await engine.dispose(close=False)
    organization_id, animal_id, actor_user_id = uuid4(), uuid4(), uuid4()
    try:
        await _insert_fixtures(
            organization_id=organization_id, animal_id=animal_id, actor_user_id=actor_user_id
        )

        async with session_factory() as session:
            await set_organization_scope(session, organization_id)
            service = ManagementAnimalService(session, organization_id)

            result = await service.update_adoption_fields(
                animal_id,
                species="狗",
                breed="米克斯",
                size="medium",
                energy="high",
                temperament=["cat_ok", "kid_ok"],
                is_adoptable=True,
                adoption_notes="親人親貓，適合有小孩的家庭",
                actor_user_id=actor_user_id,
            )

            assert result["animal"]["is_adoptable"] is True
            assert result["animal"]["size"] == "medium"
            assert result["animal"]["temperament"] == ["cat_ok", "kid_ok"]

        async with session_factory() as verify_session:
            await set_organization_scope(verify_session, organization_id)
            reloaded = await ManagementAnimalService(verify_session, organization_id).get(animal_id)
            assert reloaded["animal"]["is_adoptable"] is True
            assert reloaded["animal"]["breed"] == "米克斯"
            assert reloaded["animal"]["adoption_notes"] == "親人親貓，適合有小孩的家庭"
    finally:
        await _cleanup(organization_id=organization_id, actor_user_id=actor_user_id)
