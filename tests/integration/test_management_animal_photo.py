from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from services.api.app.api import management_animals as api
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.application.management_animal_service import ManagementAnimalService
from services.api.app.main import app


class _Result:
    def __init__(self, row):
        self.row = row

    def one_or_none(self):
        return self.row


class _Session:
    def __init__(self, row):
        self.row = row
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.row)


def _row(organization_id, animal_id, **media_overrides):
    animal = SimpleNamespace(
        id=animal_id,
        organization_id=organization_id,
        current_photo_key="animals/a/primary.jpg",
    )
    media_values = {
        "organization_id": organization_id,
        "object_key": animal.current_photo_key,
        "status": "processed",
        "exif_removed": True,
        "content_type": "image/jpeg",
    }
    media_values.update(media_overrides)
    media = SimpleNamespace(
        **media_values,
    )
    return animal, media


def _context(role, organization_id):
    return RequestContext(
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4() if organization_id else None,
        role=role,
        platform_scope=role == "PLATFORM_ADMIN",
    )


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_management_photo_requires_bearer_authentication():
    response = TestClient(app).get(f"/v1/management/animals/{uuid4()}/photo")

    assert response.status_code == 401


@pytest.mark.parametrize("role", ["STAFF", "SHELTER_ADMIN", "PLATFORM_ADMIN"])
def test_management_photo_allows_management_roles_and_returns_private_binary(monkeypatch, role):
    organization_id, animal_id = uuid4(), uuid4()
    session = _Session(_row(organization_id, animal_id))

    class Storage:
        async def get(self, *, scope, key):
            assert scope.organization_id == organization_id
            assert key == "animals/a/primary.jpg"
            return b"safe-jpeg"

    monkeypatch.setattr(api, "MinioStorageAdapter", Storage)
    app.dependency_overrides[current_request_context] = lambda: _context(role, organization_id)
    app.dependency_overrides[request_session] = lambda: session

    response = TestClient(app).get(f"/v1/management/animals/{animal_id}/photo")

    assert response.status_code == 200
    assert response.content == b"safe-jpeg"
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        (_context("VOLUNTEER", uuid4()), 403),
        (_context("STAFF", None), 409),
    ],
)
def test_management_photo_enforces_role_and_active_shelter(context, expected):
    app.dependency_overrides[current_request_context] = lambda: context
    app.dependency_overrides[request_session] = lambda: _Session(None)

    response = TestClient(app).get(f"/v1/management/animals/{uuid4()}/photo")

    assert response.status_code == expected


@pytest.mark.asyncio
async def test_management_photo_lookup_is_explicitly_tenant_scoped():
    organization_id, animal_id = uuid4(), uuid4()
    session = _Session(_row(organization_id, animal_id))

    photo = await ManagementAnimalService(session, organization_id).photo(animal_id)

    assert photo.object_key == "animals/a/primary.jpg"
    sql = " ".join(str(session.statements[0]).lower().split())
    assert "animals.organization_id" in sql
    assert "media_assets.organization_id" in sql
    assert (
        "animals.current_photo_key = media_assets.object_key" in sql
        or "media_assets.object_key = animals.current_photo_key" in sql
    )


@pytest.mark.parametrize(
    "row",
    [
        None,
        (SimpleNamespace(id=uuid4(), organization_id=uuid4(), current_photo_key=None), None),
    ],
)
def test_management_photo_hides_missing_cross_tenant_or_missing_photo(row):
    organization_id = uuid4()
    app.dependency_overrides[current_request_context] = lambda: _context("STAFF", organization_id)
    app.dependency_overrides[request_session] = lambda: _Session(row)

    response = TestClient(app).get(f"/v1/management/animals/{uuid4()}/photo")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "pending"},
        {"exif_removed": False},
        {"content_type": "image/svg+xml"},
    ],
)
def test_management_photo_rejects_untrusted_media(overrides):
    organization_id, animal_id = uuid4(), uuid4()
    app.dependency_overrides[current_request_context] = lambda: _context("STAFF", organization_id)
    app.dependency_overrides[request_session] = lambda: _Session(
        _row(organization_id, animal_id, **overrides)
    )

    response = TestClient(app).get(f"/v1/management/animals/{animal_id}/photo")

    assert response.status_code == 404


def test_management_photo_hides_storage_failure(monkeypatch, caplog):
    organization_id, animal_id = uuid4(), uuid4()

    class Storage:
        async def get(self, *, scope, key):
            raise RuntimeError("private storage detail")

    monkeypatch.setattr(api, "MinioStorageAdapter", Storage)
    app.dependency_overrides[current_request_context] = lambda: _context("STAFF", organization_id)
    app.dependency_overrides[request_session] = lambda: _Session(_row(organization_id, animal_id))

    response = TestClient(app).get(f"/v1/management/animals/{animal_id}/photo")

    assert response.status_code == 404
    assert "private storage detail" not in response.text
    assert "management animal photo storage read failed" in caplog.text
