from __future__ import annotations

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
