import os
from dataclasses import replace
from datetime import date, time
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from services.api.app.api.dependencies import (
    RequestContext,
    current_request_context,
    request_session,
)
from services.api.app.main import app
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.audit import AuditRecord
from services.api.app.persistence.models.identity import Organization, User
from services.api.app.persistence.models.medical_care import CareReminderSeries
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.mark.asyncio
async def test_real_postgres_profile_api_audit_validation_and_tenant_isolation():
    url = os.getenv(
        "STRAYHUB_TEST_DATABASE_URL", "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub"
    )
    engine = create_async_engine(
        url.replace("postgresql://", "postgresql+asyncpg://"), pool_size=1, max_overflow=0
    )
    org_a, org_b, user_id, animal_id = (uuid4() for _ in range(4))
    context = RequestContext(user_id, org_a, uuid4(), "STAFF")
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            session = AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
            async with session:
                session.add_all(
                    [
                        Organization(
                            id=org_a, name="Profile A", code=f"PA-{org_a.hex}", status="active"
                        ),
                        Organization(
                            id=org_b, name="Profile B", code=f"PB-{org_b.hex}", status="active"
                        ),
                        User(id=user_id, display_name="Profile manager", status="active"),
                    ]
                )
                await session.flush()
                session.add(
                    Animal(id=animal_id, organization_id=org_a, name="測試犬", status="active")
                )
                await session.commit()
                series = CareReminderSeries(
                    organization_id=org_a,
                    animal_id=animal_id,
                    lineage_id=uuid4(),
                    reminder_type="other",
                    title="Profile status regression",
                    anchor_local_date=date(2020, 1, 1),
                    anchor_local_time=time(9),
                    frequency="daily",
                    created_by_user_id=user_id,
                    updated_by_user_id=user_id,
                )
                session.add(series)
                await session.commit()
                await connection.execute(text("SET LOCAL ROLE strayhub_runtime"))
                await set_organization_scope(session, org_a)
                app.dependency_overrides[current_request_context] = lambda: context
                app.dependency_overrides[request_session] = lambda: session
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    path = f"/v1/management/animals/{animal_id}"
                    legacy = await client.get(path)
                    assert legacy.status_code == 200
                    assert legacy.json()["animal"]["sex"] == "unknown"
                    assert legacy.json()["animal"]["birth_date"] is None
                    for invalid_values in (
                        {"sex": "invalid"},
                        {"birth_date": date(2020, 2, 2), "intake_date": date(2020, 2, 1)},
                        {"birth_date_estimated": True},
                    ):
                        with pytest.raises(IntegrityError):
                            async with session.begin_nested():
                                await session.execute(
                                    update(Animal)
                                    .where(Animal.id == animal_id)
                                    .values(**invalid_values)
                                    .execution_options(synchronize_session=False)
                                )
                    changed = await client.patch(
                        path + "/profile",
                        json={
                            "sex": "male",
                            "breed": " 藏獒 ",
                            "intake_date": "2020-02-01",
                            "birth_date": "2019-02-01",
                            "behavior_notes": " 管理端描述 ",
                            "care_guidance": " 請先出聲 ",
                        },
                    )
                    assert changed.status_code == 200, changed.text
                    assert changed.json()["animal"]["breed"] == "藏獒"
                    assert series.status == "active"
                    await set_organization_scope(session, org_a)
                    audit = (
                        await session.execute(
                            select(AuditRecord).where(AuditRecord.resource_id == animal_id)
                        )
                    ).scalar_one()
                    assert audit.action == "animal.profile_updated"
                    assert audit.before_data["sex"] == "unknown"
                    assert audit.after_data["sex"] == "male"
                    assert audit.after_data["birth_date"] == "2019-02-01"
                    # Omitted fields remain intact; no-op edits do not add audit noise.
                    unchanged = await client.patch(path + "/profile", json={"sex": "male"})
                    assert unchanged.status_code == 200
                    await set_organization_scope(session, org_a)
                    assert (
                        await session.scalar(
                            select(func.count(AuditRecord.id)).where(
                                AuditRecord.resource_id == animal_id
                            )
                        )
                    ) == 1
                    cleared = await client.patch(path + "/profile", json={"behavior_notes": None})
                    assert cleared.status_code == 200
                    assert cleared.json()["animal"]["behavior_notes"] is None
                    assert cleared.json()["animal"]["care_guidance"] == "請先出聲"
                    await set_organization_scope(session, org_a)
                    assert (
                        await client.patch(path + "/profile", json={"intake_date": "2018-01-01"})
                    ).status_code == 422
                    assert (
                        await client.patch(path + "/profile", json={"sex": "公"})
                    ).status_code == 422
                    assert (
                        await client.patch(path + "/profile", json={"organization_id": str(org_b)})
                    ).status_code == 422
                    assert (
                        await client.patch(path, json={"status": "inactive"})
                    ).status_code == 422
                    assert (await session.get(Animal, animal_id)).intake_date == date(2020, 2, 1)
                    context = replace(context, role="VOLUNTEER")
                    assert (
                        await client.patch(path + "/profile", json={"sex": "female"})
                    ).status_code == 403
                    context = replace(context, role="STAFF", organization_id=org_b)
                    await set_organization_scope(session, org_b)
                    assert (await client.get(path)).status_code == 404
                    assert (
                        await client.patch(path + "/profile", json={"sex": "female"})
                    ).status_code == 404
                    assert (
                        await session.scalar(
                            text("SELECT count(*) FROM animals WHERE id = :id"), {"id": animal_id}
                        )
                    ) == 0
                    context = replace(context, organization_id=org_a)
                    await set_organization_scope(session, org_a)
                    status = await client.patch(
                        path, json={"status": "inactive", "reason": "Regression test"}
                    )
                    assert status.status_code == 200
                    assert status.json()["suspended_series_count"] == 1
                    assert series.status == "suspended"
                    assert status.json()["animal"]["breed"] == "藏獒"
                    await session.rollback()
            await outer.rollback()
        # The one-connection pool must not retain A's tenant or role settings.
        async with engine.connect() as reused:
            await reused.execute(text("SET LOCAL ROLE strayhub_runtime"))
            assert not await reused.scalar(
                text("SELECT nullif(current_setting('app.current_org_id', true), '')")
            )
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
