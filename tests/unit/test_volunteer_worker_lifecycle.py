from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.worker import worker
from services.worker.app.handlers import volunteer_access_handler


@pytest.mark.asyncio
async def test_worker_retries_iteration_failure_and_disposes_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Bind:
        disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    bind = Bind()
    factory = type("Factory", (), {"kw": {"bind": bind}})()
    calls = []

    async def fail_iteration(_factory, *, worker_id: str) -> None:
        calls.append(worker_id)
        raise RuntimeError("transient database failure")

    async def cancel_sleep(_seconds: int) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(worker, "create_worker_session_factory", lambda: factory)
    monkeypatch.setattr(worker, "run_volunteer_iteration", fail_iteration)
    monkeypatch.setattr(worker.asyncio, "sleep", cancel_sleep)
    monkeypatch.setenv("STRAYHUB_WORKER_ID", "worker-test")

    with pytest.raises(asyncio.CancelledError):
        await worker.run()

    assert calls == ["worker-test"]
    assert bind.disposed is True


def test_worker_registration_excludes_unapproved_adoption_ai_and_growth_diary() -> None:
    source = inspect.getsource(worker)

    assert "VolunteerAccessHandler" in source
    assert "GrowthDiary" not in source
    assert "AdoptionAi" not in source
    assert "Gemini" not in source


@pytest.mark.asyncio
@pytest.mark.parametrize("menu_failure", [False, True])
async def test_committed_approval_notification_links_menu_best_effort(
    monkeypatch: pytest.MonkeyPatch,
    menu_failure: bool,
) -> None:
    delivery = SimpleNamespace(
        line_binding_id=uuid4(),
        payload={"organization_name": "Shelter", "application_status": "approved"},
    )
    completed = []

    class Repository:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def recover_stale_notification_claims(self) -> None:
            pass

        async def claim_notifications(self, *, limit: int):
            return [delivery]

        async def recipient_line_user_id(self, _binding_id):
            return "U-approved"

        async def complete_notification(self, item, **result):
            completed.append((item, result))

    class Session:
        committed = False

        async def commit(self):
            self.committed = True

    class Messenger:
        pushes = []

        async def push(self, *, to_user_id: str, messages: list[dict]):
            self.pushes.append((to_user_id, messages))

    class Router:
        calls = []

        async def link_for_user(self, *, line_user_id: str, role: str | None):
            self.calls.append((line_user_id, role))
            if menu_failure:
                raise RuntimeError("LINE menu unavailable")

    session, messenger, router = Session(), Messenger(), Router()
    monkeypatch.setattr(
        volunteer_access_handler,
        "WorkerVolunteerAccessRepository",
        Repository,
    )
    monkeypatch.setattr(volunteer_access_handler, "_rich_menu_router", lambda: router)

    delivered = await volunteer_access_handler.VolunteerAccessHandler(
        session, worker_id="worker-test"
    ).deliver_notifications(uuid4(), messaging=messenger)

    assert delivered == 1
    assert messenger.pushes[0][0] == "U-approved"
    assert router.calls == [("U-approved", "VOLUNTEER")]
    assert completed == [(delivery, {"sent": True})]
    assert session.committed is True
