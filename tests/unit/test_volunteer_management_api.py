from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from services.api.app.api import volunteer_management as api
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.application.volunteer_management_service import VolunteerProfileResult
from services.api.app.domain.volunteer_experience import VolunteerVisitStatistics
from services.api.app.main import app


class _Session:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class _AuthenticationRepository:
    def __init__(self, _session: _Session) -> None:
        pass

    async def get_organization(self, _organization_id: UUID) -> SimpleNamespace:
        return SimpleNamespace(timezone="Asia/Taipei")


class _Service:
    def __init__(self, organization_id: UUID, membership_id: UUID) -> None:
        self.organization_id = organization_id
        self.membership = SimpleNamespace(
            id=membership_id,
            user_id=uuid4(),
            volunteer_no="V024",
            status="active",
            can_assist_new_volunteers=False,
        )
        self.incident = SimpleNamespace(
            id=uuid4(),
            incident_type="安全事件",
            severity="high",
            factual_summary="未依照牽繩安全流程",
            occurred_at=datetime(2026, 9, 3, 2, tzinfo=timezone.utc),
            status="reported",
        )
        self.restriction = SimpleNamespace(
            id=uuid4(),
            organization_id=organization_id,
            scope="PLATFORM",
            reason_category="service_safety",
            status="pending_review",
            starts_at=datetime(2026, 9, 3, 2, tzinfo=timezone.utc),
            ends_at=None,
            reviewed_at=None,
        )
        self.calls: list[tuple[str, object]] = []

    async def detail(self, membership_id: UUID, **kwargs) -> VolunteerProfileResult:
        self.calls.append(("detail", membership_id))
        assert kwargs["as_of"] == date(2026, 9, 4)
        note = SimpleNamespace(
            id=uuid4(),
            content="熟悉犬舍流程",
            created_at=datetime(2026, 9, 3, 1, tzinfo=timezone.utc),
        )
        return VolunteerProfileResult(
            membership=self.membership,
            surname="黃",
            statistics=VolunteerVisitStatistics(
                current_shelter_visits=2,
                total_strayhub_visits=8,
                visits_last_180_days=6,
                visits_last_90_days=4,
                visits_last_30_days=1,
                last_visit_at=datetime(2026, 9, 2, 4, tzinfo=timezone.utc),
                active_months_last_6_months=4,
                recent_status="consistently_active",
            ),
            notes=[(note, "本所管理員")],
            incidents=[self.incident],
            restrictions=[self.restriction],
        )

    async def add_note(self, membership_id: UUID, **kwargs) -> SimpleNamespace:
        self.calls.append(("add_note", kwargs["content"]))
        return SimpleNamespace(
            id=uuid4(),
            content=kwargs["content"],
            created_at=datetime(2026, 9, 4, 1, tzinfo=timezone.utc),
        )

    async def set_assist_flag(self, membership_id: UUID, **kwargs) -> SimpleNamespace:
        self.calls.append(("set_assist_flag", kwargs["value"]))
        self.membership.can_assist_new_volunteers = kwargs["value"]
        return self.membership

    async def add_incident(self, membership_id: UUID, **kwargs) -> SimpleNamespace:
        self.calls.append(("add_incident", kwargs["incident_type"]))
        return self.incident

    async def review_incident(self, incident_id: UUID, **kwargs) -> SimpleNamespace:
        self.calls.append(("review_incident", kwargs["decision"]))
        self.incident.status = "confirmed"
        return self.incident

    async def request_restriction(self, incident_id: UUID, **kwargs) -> SimpleNamespace:
        self.calls.append(("request_restriction", kwargs["scope"]))
        return self.restriction

    async def list_pending_platform_restrictions(self, **kwargs):
        self.calls.append(("list_pending_platform_restrictions", self.restriction.id))
        return [(self.restriction, self.incident, "安心動物之家")]

    async def decide_platform_restriction(self, restriction_id: UUID, **kwargs) -> SimpleNamespace:
        self.calls.append(("decide_platform_restriction", kwargs["decision"]))
        self.restriction.status = "active"
        self.restriction.reviewed_at = datetime(2026, 9, 4, 3, tzinfo=timezone.utc)
        return self.restriction


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _context(organization_id: UUID, *, platform: bool = False) -> RequestContext:
    return RequestContext(
        user_id=uuid4(),
        organization_id=None if platform else organization_id,
        membership_id=None if platform else uuid4(),
        role="PLATFORM_ADMIN" if platform else "SHELTER_ADMIN",
        platform_scope=platform,
    )


def test_volunteer_management_routes_require_authentication() -> None:
    response = TestClient(app).get(f"/v1/organizations/{uuid4()}/volunteers/{uuid4()}")

    assert response.status_code == 401


def test_shelter_volunteer_management_http_contract(monkeypatch) -> None:
    organization_id, membership_id = uuid4(), uuid4()
    session = _Session()
    service = _Service(organization_id, membership_id)
    monkeypatch.setattr(api, "AuthenticationRepository", _AuthenticationRepository)
    monkeypatch.setattr(api, "local_today", lambda _timezone: date(2026, 9, 4))
    monkeypatch.setattr(api, "_service", lambda _session, _organization_id: service)
    app.dependency_overrides[current_request_context] = lambda: _context(organization_id)
    app.dependency_overrides[request_session] = lambda: session
    client = TestClient(app)
    root = f"/v1/organizations/{organization_id}"

    profile = client.get(f"{root}/volunteers/{membership_id}")
    note = client.post(f"{root}/volunteers/{membership_id}/notes", json={"content": "後續觀察"})
    assist = client.patch(
        f"{root}/volunteers/{membership_id}/assist-flag",
        json={"can_assist_new_volunteers": True},
    )
    incident = client.post(
        f"{root}/volunteers/{membership_id}/incidents",
        json={
            "incident_type": "安全事件",
            "severity": "high",
            "factual_summary": "未依照牽繩安全流程",
            "occurred_at": "2026-09-03T02:00:00Z",
        },
    )
    reviewed = client.post(
        f"{root}/volunteer-incidents/{service.incident.id}/decision",
        json={"decision": "confirm"},
    )
    restriction = client.post(
        f"{root}/volunteer-incidents/{service.incident.id}/restrictions",
        json={
            "scope": "PLATFORM",
            "reason_category": "service_safety",
            "starts_at": "2026-09-03T02:00:00Z",
            "ends_at": None,
        },
    )

    assert profile.status_code == 200
    assert profile.json()["label"] == "黃・V024"
    assert profile.json()["statistics"]["total_strayhub_visits"] == 8
    assert profile.json()["notes"][0]["author_display_name"] == "本所管理員"
    assert note.status_code == 201
    assert note.json()["content"] == "後續觀察"
    assert assist.json() == {"can_assist_new_volunteers": True}
    assert incident.status_code == 201
    assert reviewed.json()["status"] == "confirmed"
    assert restriction.status_code == 201
    assert restriction.json()["status"] == "pending_review"
    assert session.commits == 6


def test_platform_restriction_review_http_contract(monkeypatch) -> None:
    organization_id, membership_id = uuid4(), uuid4()
    session = _Session()
    service = _Service(organization_id, membership_id)
    monkeypatch.setattr(api, "_service", lambda _session, _organization_id: service)
    app.dependency_overrides[current_request_context] = lambda: _context(
        organization_id, platform=True
    )
    app.dependency_overrides[request_session] = lambda: session
    client = TestClient(app)

    listed = client.get("/v1/platform/volunteer-restrictions")
    decided = client.post(
        f"/v1/platform/volunteer-restrictions/{service.restriction.id}/decision",
        json={"decision": "approve", "reason": "完成正式審查"},
    )

    assert listed.status_code == 200
    assert listed.json()[0]["originating_organization_name"] == "安心動物之家"
    assert listed.json()[0]["incident"]["factual_summary"] == "未依照牽繩安全流程"
    assert decided.status_code == 200
    assert decided.json()["status"] == "active"
    assert session.commits == 2
