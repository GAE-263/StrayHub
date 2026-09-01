from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import asyncpg
from fastapi.testclient import TestClient
from services.api.app.api import media as media_api
from services.api.app.application.media_access import issue_adoption_photo_token
from services.api.app.main import app
from services.api.app.persistence.database.engine import engine


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub_test",
    )


async def _seed(organization_id: UUID, animal_id: UUID, media_id: UUID, object_key: str) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Public Photo Shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"PHOTO-{organization_id.hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, status, is_adoptable, current_photo_key,
                 created_at, updated_at)
            VALUES ($1, $2, '有照片的毛孩', 'active', true, $3, now(), now())
            """,
            animal_id,
            organization_id,
            object_key,
        )
        await connection.execute(
            """
            INSERT INTO media_assets
                (id, organization_id, object_key, content_type, checksum, status,
                 purpose, exif_removed, created_at, updated_at)
            VALUES ($1, $2, $3, 'image/jpeg', $4, 'processed',
                    'animal_primary', true, now(), now())
            """,
            media_id,
            organization_id,
            object_key,
            "a" * 64,
        )
    finally:
        await connection.close()


async def _set_not_adoptable(organization_id: UUID, animal_id: UUID) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute(
            "UPDATE animals SET is_adoptable = false WHERE organization_id = $1 AND id = $2",
            organization_id,
            animal_id,
        )
    finally:
        await connection.close()


async def _cleanup(organization_id: UUID) -> None:
    connection = await asyncpg.connect(_database_url())
    try:
        await connection.execute(
            "DELETE FROM media_assets WHERE organization_id = $1", organization_id
        )
        await connection.execute("DELETE FROM animals WHERE organization_id = $1", organization_id)
        await connection.execute("DELETE FROM organizations WHERE id = $1", organization_id)
    finally:
        await connection.close()


def test_public_adoption_photo_streams_private_media_only_while_adoptable(monkeypatch) -> None:
    organization_id, animal_id, media_id = uuid4(), uuid4(), uuid4()
    object_key = f"test/adoption/{animal_id}/primary.jpg"
    photo_bytes = b"safe-sanitized-jpeg-bytes"

    class Storage:
        async def get(self, *, scope, key):
            assert scope.organization_id == organization_id
            assert key == object_key
            return photo_bytes

    monkeypatch.setattr(media_api, "MinioStorageAdapter", Storage)
    asyncio.run(_seed(organization_id, animal_id, media_id, object_key))
    try:
        asyncio.run(engine.dispose(close=False))
        client = TestClient(app)
        token = issue_adoption_photo_token(
            organization_id=organization_id,
            animal_id=animal_id,
            object_key=object_key,
        )
        url = f"/v1/public/adoption/animals/{animal_id}/photo?token={token}"

        response = client.get(url)
        assert response.status_code == 200
        assert response.content == photo_bytes
        assert response.headers["content-type"] == "image/jpeg"
        assert response.headers["x-content-type-options"] == "nosniff"

        asyncio.run(_set_not_adoptable(organization_id, animal_id))
        asyncio.run(engine.dispose(close=False))
        denied = client.get(url)
        assert denied.status_code == 404
    finally:
        asyncio.run(engine.dispose(close=False))
        asyncio.run(_cleanup(organization_id))
