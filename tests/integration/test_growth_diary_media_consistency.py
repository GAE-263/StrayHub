import hashlib
import inspect
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image
from services.api.app.api.errors import DomainError
from services.api.app.api.line_webhook import _growth_diary_event_transaction
from services.api.app.application.media_service import MediaProcessingService
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.api.app.persistence.models.growth_diary import GrowthDiaryEntry
from services.api.app.persistence.repositories.growth_diary_repository import GrowthDiaryRepository


class _ScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _RepositorySession:
    def __init__(self, query_values: list[object]) -> None:
        self.query_values = iter(query_values)
        self.added: list[object] = []

    async def execute(self, _statement):
        return _ScalarResult(next(self.query_values))

    def add(self, value) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None


class _TransactionContext:
    def __init__(self, commit_error: Exception | None = None) -> None:
        self.commit_error = commit_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, _exc, _traceback):
        if exc_type is None and self.commit_error is not None:
            raise self.commit_error
        return False


class _TransactionSession:
    def __init__(self, commit_error: Exception | None = None) -> None:
        self.commit_error = commit_error

    def begin(self):
        return _TransactionContext(self.commit_error)


class _TrackingStorage(InMemoryStorageFake):
    def __init__(self, *, delete_error: Exception | None = None) -> None:
        super().__init__()
        self.deleted: list[tuple[object, str]] = []
        self.delete_error = delete_error

    async def delete(self, *, scope, key: str) -> None:
        self.deleted.append((scope, key))
        if self.delete_error is not None:
            raise self.delete_error
        await super().delete(scope=scope, key=key)


class _BackgroundTasks:
    def __init__(self, *, add_error: Exception | None = None) -> None:
        self.tasks: list[tuple[object, tuple, dict]] = []
        self.add_error = add_error

    def add_task(self, function, *args, **kwargs) -> None:
        if self.add_error is not None:
            raise self.add_error
        self.tasks.append((function, args, kwargs))


def _jpeg_with_metadata() -> bytes:
    output = BytesIO()
    exif = Image.Exif()
    exif[315] = "must-not-reach-storage"
    Image.new("RGB", (2_000, 1_000), "purple").save(output, format="JPEG", exif=exif)
    return output.getvalue()


@pytest.mark.asyncio
async def test_growth_diary_storage_receives_only_final_webp_and_metadata() -> None:
    storage = InMemoryStorageFake()
    organization_id = uuid4()
    object_key = "growth-diary/event-1/photo.webp"

    stored = await MediaProcessingService(storage).store_cleaned(
        organization_id=organization_id,
        object_key=object_key,
        data=_jpeg_with_metadata(),
        declared_content_type="image/jpeg",
        output_policy="growth_diary_webp",
    )

    final_bytes = await storage.get(scope=stored.scope, key=stored.key)
    metadata = storage.metadata(scope=stored.scope, key=stored.key)
    with Image.open(BytesIO(final_bytes)) as image:
        assert image.format == "WEBP"
        assert max(image.size) == 1_600
        assert not image.getexif()

    assert stored.metadata == metadata
    assert metadata.content_type == "image/webp"
    assert metadata.size == len(final_bytes)
    assert metadata.checksum == hashlib.sha256(final_bytes).hexdigest()
    assert set(storage._objects) == {(organization_id, object_key)}


@pytest.mark.asyncio
async def test_repository_persists_final_photo_type_after_tenant_validation() -> None:
    organization_id = uuid4()
    inquiry_id, animal_id, adopter_user_id = uuid4(), uuid4(), uuid4()
    session = _RepositorySession(
        [
            SimpleNamespace(
                id=inquiry_id,
                organization_id=organization_id,
                target_animal_id=animal_id,
                adopter_user_id=adopter_user_id,
            ),
            SimpleNamespace(id=animal_id, organization_id=organization_id),
        ]
    )

    entry = await GrowthDiaryRepository(session, organization_id).add_entry(
        inquiry_id=inquiry_id,
        animal_id=animal_id,
        adopter_user_id=adopter_user_id,
        photo_key="growth-diary/event-1/photo.webp",
        photo_content_type="image/webp",
        note=None,
    )

    assert entry.organization_id == organization_id
    assert entry.photo_content_type == "image/webp"
    assert session.added == [entry]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("photo_key", "photo_content_type", "note"),
    [
        (None, None, None),
        ("growth-diary/event/photo.webp", None, None),
        ("growth-diary/event/photo.webp", "image/jpeg", None),
    ],
)
async def test_repository_rejects_empty_or_untrusted_new_photo_entries(
    photo_key, photo_content_type, note
) -> None:
    repository = GrowthDiaryRepository(_RepositorySession([]), uuid4())

    with pytest.raises(DomainError):
        await repository.add_entry(
            inquiry_id=uuid4(),
            animal_id=uuid4(),
            adopter_user_id=uuid4(),
            photo_key=photo_key,
            photo_content_type=photo_content_type,
            note=note,
        )


@pytest.mark.asyncio
async def test_repository_rejects_cross_tenant_or_mismatched_inquiry_animal() -> None:
    organization_id = uuid4()
    repository = GrowthDiaryRepository(_RepositorySession([None]), organization_id)

    with pytest.raises(DomainError, match="不存在或無法存取"):
        await repository.add_entry(
            inquiry_id=uuid4(),
            animal_id=uuid4(),
            adopter_user_id=uuid4(),
            photo_key=None,
            photo_content_type=None,
            note="valid note",
        )


def test_repository_does_not_accept_client_organization_override_and_legacy_is_nullable() -> None:
    parameters = inspect.signature(GrowthDiaryRepository.add_entry).parameters
    assert "organization_id" not in parameters

    legacy = GrowthDiaryEntry(
        organization_id=uuid4(),
        inquiry_id=uuid4(),
        animal_id=uuid4(),
        adopter_user_id=uuid4(),
        photo_key="legacy/photo.jpg",
        note=None,
    )
    assert legacy.photo_content_type is None
    assert legacy.ai_analysis_status is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["flush", "commit"])
async def test_event_transaction_deletes_stored_object_on_database_failure(failure_point) -> None:
    root_error = RuntimeError(f"database {failure_point} failed")
    session = _TransactionSession(root_error if failure_point == "commit" else None)
    storage = _TrackingStorage()
    background_tasks = _BackgroundTasks()
    organization_id = uuid4()
    key = "growth-diary/event/photo.webp"
    storage._objects[(organization_id, key)] = (b"webp", SimpleNamespace())

    with pytest.raises(RuntimeError, match=failure_point):
        async with _growth_diary_event_transaction(
            session,
            event_id="event-1",
            background_tasks=background_tasks,
        ) as boundary:
            boundary.register_stored_photo(
                storage=storage,
                organization_id=organization_id,
                object_key=key,
            )
            if failure_point == "flush":
                raise root_error

    assert [(item[0].organization_id, item[1]) for item in storage.deleted] == [
        (organization_id, key)
    ]
    assert (organization_id, key) not in storage._objects
    assert background_tasks.tasks == []


@pytest.mark.asyncio
async def test_cleanup_failure_is_logged_without_replacing_database_root_cause(caplog) -> None:
    storage = _TrackingStorage(delete_error=RuntimeError("delete failed"))
    root_error = RuntimeError("database commit failed")

    with pytest.raises(RuntimeError, match="database commit failed"):
        async with _growth_diary_event_transaction(
            _TransactionSession(root_error),
            event_id="event-2",
            background_tasks=_BackgroundTasks(),
        ) as boundary:
            boundary.register_stored_photo(
                storage=storage,
                organization_id=uuid4(),
                object_key="must-not-appear-in-log.webp",
            )

    assert "growth_diary_orphan_cleanup_failed" in caplog.text
    assert "must-not-appear-in-log.webp" not in caplog.text


@pytest.mark.asyncio
async def test_post_commit_side_effect_failure_never_deletes_durable_photo(monkeypatch) -> None:
    storage = _TrackingStorage()
    background_tasks = _BackgroundTasks(add_error=RuntimeError("task registration failed"))
    organization_id = uuid4()
    key = "growth-diary/event/photo.webp"
    storage._objects[(organization_id, key)] = (b"webp", SimpleNamespace())

    async def failed_reply(*_args, **_kwargs):
        raise RuntimeError("reply failed")

    monkeypatch.setattr("services.api.app.api.line_webhook._reply", failed_reply)

    async with _growth_diary_event_transaction(
        _TransactionSession(),
        event_id="event-3",
        background_tasks=background_tasks,
    ) as boundary:
        boundary.register_stored_photo(
            storage=storage,
            organization_id=organization_id,
            object_key=key,
        )
        boundary.prepare_success(
            line=object(),
            event={},
            line_user_id="U123",
            organization_id=organization_id,
            entry_id=uuid4(),
            animal_name="旺來",
            note="今天很好",
            has_photo=True,
        )

    assert storage.deleted == []
    assert (organization_id, key) in storage._objects
