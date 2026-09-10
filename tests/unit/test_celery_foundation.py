from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from services.api.app.infrastructure.celery_app import celery_app
from services.worker.app.celery_runtime import CeleryAsyncRuntime


def test_celery_uses_explicit_routes_without_result_backend() -> None:
    assert celery_app.conf.task_ignore_result is True
    assert celery_app.backend.as_uri() == "disabled://"
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.task_routes["adoption.*"]["queue"] == "ai"
    assert celery_app.conf.task_routes["growth_diary.*"]["queue"] == "ai"
    assert celery_app.conf.task_routes["system.*"]["queue"] == "system"


def test_async_runtime_reuses_one_event_loop_and_disposes_cleanly() -> None:
    worker_runtime = CeleryAsyncRuntime()

    async def loop_identity(_factory) -> int:
        import asyncio

        return id(asyncio.get_running_loop())

    first = worker_runtime.run(loop_identity)
    second = worker_runtime.run(loop_identity)
    worker_runtime.close()

    assert first == second


def test_profile_followup_dispatch_receives_the_worker_runtime_factory(monkeypatch) -> None:
    from services.worker.app.tasks import adoption

    worker_runtime = CeleryAsyncRuntime()
    next_job_id, organization_id = uuid4(), uuid4()
    dispatch = AsyncMock(return_value=True)
    claim = AsyncMock(return_value=SimpleNamespace(skip_ai_reason="disabled"))
    apply = AsyncMock(return_value=SimpleNamespace(applied=True, next_job_id=next_job_id))
    monkeypatch.setattr(adoption, "runtime", worker_runtime)
    monkeypatch.setattr(adoption, "claim_profile_extraction_job", claim)
    monkeypatch.setattr(adoption, "apply_profile_extraction_result", apply)
    monkeypatch.setattr(adoption, "dispatch_ai_job", dispatch)
    monkeypatch.setattr(
        adoption, "_deliver_profile_notification", lambda *args, **kwargs: "stubbed"
    )
    try:
        assert (
            adoption.extract_profile.run(
                job_id=str(uuid4()),
                resource_id=str(uuid4()),
                organization_id=str(organization_id),
                expected_version=1,
            )
            == "stubbed"
        )
        dispatch.assert_awaited_once_with(
            next_job_id, organization_id, factory=worker_runtime._factory
        )
        assert claim.await_args.args[0] is worker_runtime._factory
        assert apply.await_args.args[0] is worker_runtime._factory
    finally:
        worker_runtime.close()
