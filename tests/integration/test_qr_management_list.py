from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.application.qr_token_service import issue_printable_qr_token
from services.api.app.main import app
from services.api.app.persistence.database.scope import set_platform_scope
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.identity import Organization
from services.api.app.persistence.models.qr_code import AnimalQrCode
from services.api.app.persistence.models.shelter_area import ShelterArea
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


def _qr(
    *,
    organization_id: UUID,
    animal_id: UUID,
    created_at: datetime,
    status: str = "active",
    revoked: bool = False,
    qr_id: UUID | None = None,
    printable: bool = False,
) -> AnimalQrCode:
    qr_id = qr_id or uuid4()
    raw_token = issue_printable_qr_token(qr_id) if printable else f"legacy-{qr_id}"
    return AnimalQrCode(
        id=qr_id,
        organization_id=organization_id,
        animal_id=animal_id,
        token_digest=hashlib.sha256(raw_token.encode()).hexdigest(),
        status=status,
        revoked=revoked,
        created_at=created_at,
        updated_at=created_at,
    )


@pytest.mark.asyncio
async def test_qr_management_list_search_status_pagination_and_tenant_safety() -> None:
    url = os.environ["STRAYHUB_TEST_DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    org_a, org_b = uuid4(), uuid4()
    area_a, inactive_area_a, area_b = uuid4(), uuid4(), uuid4()
    animal_main, animal_latin, animal_percent, animal_underscore = (uuid4() for _ in range(4))
    animal_backslash, animal_backslash_decoy = uuid4(), uuid4()
    animal_percent_decoy, animal_underscore_decoy, animal_null = (uuid4() for _ in range(3))
    animal_foreign_area, animal_drift_active, animal_drift_revoked = (uuid4() for _ in range(3))
    animal_stable, animal_b = uuid4(), uuid4()
    now = datetime(2026, 8, 20, 6, 30, tzinfo=timezone.utc)
    active_qr_id = UUID("ffffffff-ffff-ffff-ffff-fffffffffff0")
    stable_low = UUID("00000000-0000-0000-0000-000000000001")
    stable_high = UUID("00000000-0000-0000-0000-000000000002")
    context = RequestContext(uuid4(), org_a, None, "PLATFORM_ADMIN", platform_scope=True)
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            session = AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            async with session:
                session.add_all(
                    [
                        Organization(
                            id=org_a, name="QR Org A", code=f"QR-A-{org_a.hex}", status="active"
                        ),
                        Organization(
                            id=org_b, name="QR Org B", code=f"QR-B-{org_b.hex}", status="active"
                        ),
                    ]
                )
                await session.flush()
                session.add_all(
                    [
                        ShelterArea(
                            id=area_a,
                            organization_id=org_a,
                            name="犬舍 A3",
                            area_type="cage",
                            status="active",
                        ),
                        ShelterArea(
                            id=inactive_area_a,
                            organization_id=org_a,
                            name="舊犬舍",
                            area_type="cage",
                            status="inactive",
                        ),
                        ShelterArea(
                            id=area_b,
                            organization_id=org_b,
                            name="不可洩漏的 B 區",
                            area_type="cage",
                            status="active",
                        ),
                    ]
                )
                await session.flush()
                session.add_all(
                    [
                        Animal(
                            id=animal_main,
                            organization_id=org_a,
                            name="小黑",
                            shelter_number="A-013",
                            area_id=area_a,
                            status="active",
                        ),
                        Animal(
                            id=animal_latin,
                            organization_id=org_a,
                            name="Black Dog",
                            shelter_number="LAT-100",
                            area_id=inactive_area_a,
                            status="inactive",
                        ),
                        Animal(
                            id=animal_percent,
                            organization_id=org_a,
                            name="百分%犬",
                            shelter_number="PERCENT",
                            status="active",
                        ),
                        Animal(
                            id=animal_underscore,
                            organization_id=org_a,
                            name="底線_犬",
                            shelter_number="UNDER",
                            status="active",
                        ),
                        Animal(
                            id=animal_percent_decoy,
                            organization_id=org_a,
                            name="百分X犬",
                            shelter_number="PERCENT-X",
                            status="active",
                        ),
                        Animal(
                            id=animal_underscore_decoy,
                            organization_id=org_a,
                            name="底線X犬",
                            shelter_number="UNDER-X",
                            status="active",
                        ),
                        Animal(
                            id=animal_backslash,
                            organization_id=org_a,
                            name="反斜\\犬",
                            shelter_number="BACKSLASH",
                            status="active",
                        ),
                        Animal(
                            id=animal_backslash_decoy,
                            organization_id=org_a,
                            name="反斜X犬",
                            shelter_number="BACKSLASH-X",
                            status="active",
                        ),
                        Animal(
                            id=animal_null,
                            organization_id=org_a,
                            name="無編號",
                            shelter_number=None,
                            area_id=None,
                            status="active",
                        ),
                        Animal(
                            id=animal_foreign_area,
                            organization_id=org_a,
                            name="跨區域防護",
                            shelter_number="AREA-SAFE",
                            area_id=area_b,
                            status="active",
                        ),
                        Animal(
                            id=animal_drift_active,
                            organization_id=org_a,
                            name="漂移一",
                            shelter_number="DRIFT-1",
                            status="active",
                        ),
                        Animal(
                            id=animal_drift_revoked,
                            organization_id=org_a,
                            name="漂移二",
                            shelter_number="DRIFT-2",
                            status="active",
                        ),
                        Animal(
                            id=animal_stable,
                            organization_id=org_a,
                            name="穩定排序",
                            shelter_number="ORDER-1",
                            status="active",
                        ),
                        Animal(
                            id=animal_b,
                            organization_id=org_b,
                            name="小黑",
                            shelter_number="A-013",
                            area_id=area_b,
                            status="active",
                        ),
                    ]
                )
                await session.flush()

                records = [
                    _qr(
                        qr_id=active_qr_id,
                        organization_id=org_a,
                        animal_id=animal_main,
                        created_at=now,
                        printable=True,
                    )
                ]
                records.extend(
                    _qr(
                        organization_id=org_a,
                        animal_id=animal_main,
                        created_at=now - timedelta(days=index + 1),
                        status="revoked",
                        revoked=True,
                    )
                    for index in range(21)
                )
                records.extend(
                    [
                        _qr(
                            organization_id=org_a,
                            animal_id=animal_latin,
                            created_at=now - timedelta(hours=1),
                            status="revoked",
                            revoked=True,
                        ),
                        _qr(
                            organization_id=org_a,
                            animal_id=animal_percent,
                            created_at=now - timedelta(hours=2),
                        ),
                        _qr(
                            organization_id=org_a,
                            animal_id=animal_underscore,
                            created_at=now - timedelta(hours=3),
                        ),
                        _qr(
                            organization_id=org_a,
                            animal_id=animal_percent_decoy,
                            created_at=now - timedelta(hours=4),
                        ),
                        _qr(
                            organization_id=org_a,
                            animal_id=animal_underscore_decoy,
                            created_at=now - timedelta(hours=5),
                        ),
                        _qr(
                            organization_id=org_a,
                            animal_id=animal_backslash,
                            created_at=now - timedelta(hours=5, minutes=10),
                        ),
                        _qr(
                            organization_id=org_a,
                            animal_id=animal_backslash_decoy,
                            created_at=now - timedelta(hours=5, minutes=20),
                        ),
                        _qr(
                            organization_id=org_a,
                            animal_id=animal_null,
                            created_at=now - timedelta(hours=6),
                        ),
                        _qr(
                            organization_id=org_a,
                            animal_id=animal_foreign_area,
                            created_at=now - timedelta(hours=7),
                        ),
                        _qr(
                            organization_id=org_a,
                            animal_id=animal_drift_active,
                            created_at=now - timedelta(hours=8),
                            status="active",
                            revoked=True,
                        ),
                        _qr(
                            organization_id=org_a,
                            animal_id=animal_drift_revoked,
                            created_at=now - timedelta(hours=9),
                            status="revoked",
                            revoked=False,
                        ),
                        _qr(
                            qr_id=stable_low,
                            organization_id=org_a,
                            animal_id=animal_stable,
                            created_at=now - timedelta(hours=10),
                            status="revoked",
                            revoked=True,
                        ),
                        _qr(
                            qr_id=stable_high,
                            organization_id=org_a,
                            animal_id=animal_stable,
                            created_at=now - timedelta(hours=10),
                            status="revoked",
                            revoked=True,
                        ),
                        _qr(
                            organization_id=org_b,
                            animal_id=animal_b,
                            created_at=now + timedelta(days=1),
                        ),
                        # The FK permits this corrupt cross-organization association.
                        # The management join must reject it explicitly.
                        _qr(
                            organization_id=org_a,
                            animal_id=animal_b,
                            created_at=now + timedelta(days=2),
                        ),
                    ]
                )
                session.add_all(records)
                await session.commit()

                await connection.execute(text("SET LOCAL ROLE strayhub_runtime"))
                await set_platform_scope(session)
                app.dependency_overrides[current_request_context] = lambda: context
                app.dependency_overrides[request_session] = lambda: session
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    endpoint = "/v1/management/qr-codes"

                    default_response = await client.get(endpoint)
                    assert default_response.status_code == 200, default_response.text
                    default_body = default_response.json()
                    assert default_body["page"] == 1
                    assert default_body["page_size"] == 20
                    assert default_body["total"] == len(records) - 2
                    assert all(
                        item["organization_id"] == str(org_a) for item in default_body["items"]
                    )
                    explicit_all = await client.get(endpoint, params={"status": "all"})
                    assert explicit_all.json() == default_body

                    for query in ("A-013", "013", "小黑", "小", "  小黑  "):
                        response = await client.get(endpoint, params={"query": query})
                        assert response.status_code == 200
                        assert response.json()["total"] == 22
                        assert {item["animal_id"] for item in response.json()["items"]} == {
                            str(animal_main)
                        }

                    latin = await client.get(endpoint, params={"query": "bLaCk"})
                    assert latin.json()["total"] == 1
                    assert latin.json()["items"][0]["animal_status"] == "inactive"
                    assert latin.json()["items"][0]["area_name"] is None

                    whitespace = await client.get(endpoint, params={"query": "   "})
                    assert whitespace.json()["total"] == default_body["total"]

                    literal_percent = await client.get(endpoint, params={"query": "%"})
                    assert literal_percent.json()["total"] == 1
                    assert literal_percent.json()["items"][0]["animal_id"] == str(animal_percent)
                    literal_underscore = await client.get(endpoint, params={"query": "_"})
                    assert literal_underscore.json()["total"] == 1
                    assert literal_underscore.json()["items"][0]["animal_id"] == str(
                        animal_underscore
                    )
                    literal_backslash = await client.get(endpoint, params={"query": "\\"})
                    assert literal_backslash.json()["total"] == 1
                    assert literal_backslash.json()["items"][0]["animal_id"] == str(
                        animal_backslash
                    )

                    nulls = await client.get(endpoint, params={"animal_id": str(animal_null)})
                    null_item = nulls.json()["items"][0]
                    assert null_item["animal_name"] == "無編號"
                    assert null_item["shelter_number"] is None
                    assert null_item["area_name"] is None
                    parsed_created_at = datetime.fromisoformat(
                        null_item["created_at"].replace("Z", "+00:00")
                    )
                    assert parsed_created_at == now - timedelta(hours=6)

                    foreign_area = await client.get(
                        endpoint, params={"animal_id": str(animal_foreign_area)}
                    )
                    assert foreign_area.json()["items"][0]["area_name"] is None

                    for drift_animal in (animal_drift_active, animal_drift_revoked):
                        active = await client.get(
                            endpoint,
                            params={"animal_id": str(drift_animal), "status": "active"},
                        )
                        assert active.json()["total"] == 0
                        revoked = await client.get(
                            endpoint,
                            params={"animal_id": str(drift_animal), "status": "revoked"},
                        )
                        assert revoked.json()["total"] == 1

                    current = await client.get(endpoint, params={"animal_id": str(animal_main)})
                    current_body = current.json()
                    assert current_body["total"] == 22
                    assert current_body["items"][0]["id"] == str(active_qr_id)
                    assert current_body["items"][0]["status"] == "active"
                    assert current_body["items"][0]["revoked"] is False
                    assert current_body["items"][0]["deep_link"] is not None
                    assert current_body["items"][0]["token"] is None

                    second_page = await client.get(
                        endpoint,
                        params={"animal_id": str(animal_main), "page": 2},
                    )
                    assert second_page.json()["page"] == 2
                    assert len(second_page.json()["items"]) == 2
                    assert second_page.json()["total"] == 22
                    beyond = await client.get(
                        endpoint,
                        params={"animal_id": str(animal_main), "page": 999},
                    )
                    assert beyond.json()["items"] == []
                    assert beyond.json()["total"] == 22

                    stable = await client.get(
                        endpoint,
                        params={"animal_id": str(animal_stable), "page_size": 100},
                    )
                    assert [item["id"] for item in stable.json()["items"]] == [
                        str(stable_high),
                        str(stable_low),
                    ]

                    foreign_animal = await client.get(endpoint, params={"animal_id": str(animal_b)})
                    assert foreign_animal.json() == {
                        "items": [],
                        "page": 1,
                        "page_size": 20,
                        "total": 0,
                    }

                    for params in (
                        {"status": "invalid"},
                        {"page": 0},
                        {"page_size": 0},
                        {"page_size": 101},
                    ):
                        assert (await client.get(endpoint, params=params)).status_code == 422

                await session.rollback()
            await outer.rollback()
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
