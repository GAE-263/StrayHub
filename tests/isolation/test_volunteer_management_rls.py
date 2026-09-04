from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest


def _database_url() -> str:
    value = os.environ.get("STRAYHUB_TEST_DATABASE_URL")
    if not value:
        raise RuntimeError("STRAYHUB_TEST_DATABASE_URL is required")
    return value


@pytest.mark.asyncio
async def test_notes_incidents_and_shelter_restrictions_are_tenant_isolated() -> None:
    connection = await asyncpg.connect(_database_url())
    org_a, org_b = uuid4(), uuid4()
    admin_a, admin_b, volunteer = uuid4(), uuid4(), uuid4()
    admin_membership_a, admin_membership_b = uuid4(), uuid4()
    volunteer_membership_a, volunteer_membership_b = uuid4(), uuid4()
    note_a, note_b, incident_a, incident_b, restriction_b = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    now = datetime.now(timezone.utc)
    try:
        await connection.executemany(
            """INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'active', $4, $4)""",
            [
                (org_a, "RLS A", f"VM-A-{org_a.hex[:10]}", now),
                (org_b, "RLS B", f"VM-B-{org_b.hex[:10]}", now),
            ],
        )
        await connection.executemany(
            """INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'active', $4, $4)""",
            [
                (admin_a, f"admin-a-{admin_a.hex}", "Admin A", now),
                (admin_b, f"admin-b-{admin_b.hex}", "Admin B", now),
                (volunteer, f"volunteer-{volunteer.hex}", "Volunteer", now),
            ],
        )
        await connection.executemany(
            """INSERT INTO organization_memberships
              (id, organization_id, user_id, role, status, volunteer_no,
               valid_from, expires_at, access_version, created_at, updated_at)
            VALUES ($1,$2,$3,$4,'active',$5,$6,$7,0,$6,$6)""",
            [
                (admin_membership_a, org_a, admin_a, "SHELTER_ADMIN", None, now, None),
                (admin_membership_b, org_b, admin_b, "SHELTER_ADMIN", None, now, None),
                (
                    volunteer_membership_a,
                    org_a,
                    volunteer,
                    "VOLUNTEER",
                    "V001",
                    now,
                    now + timedelta(days=1),
                ),
                (
                    volunteer_membership_b,
                    org_b,
                    volunteer,
                    "VOLUNTEER",
                    "V001",
                    now,
                    now + timedelta(days=1),
                ),
            ],
        )
        await connection.execute(
            """INSERT INTO volunteer_profiles
              (user_id, surname, created_at, updated_at) VALUES ($1, '黃', $2, $2)""",
            volunteer,
            now,
        )
        await connection.executemany(
            """INSERT INTO volunteer_notes
              (id, organization_id, subject_membership_id, author_membership_id,
               content, created_at, updated_at) VALUES ($1,$2,$3,$4,$5,$6,$6)""",
            [
                (note_a, org_a, volunteer_membership_a, admin_membership_a, "note-a", now),
                (note_b, org_b, volunteer_membership_b, admin_membership_b, "note-b", now),
            ],
        )
        await connection.executemany(
            """INSERT INTO volunteer_incidents
              (id, organization_id, subject_membership_id, volunteer_user_id,
               incident_type, severity, factual_summary, occurred_at,
               created_by_membership_id, status, created_at, updated_at)
            VALUES ($1,$2,$3,$4,'safety','high',$5,$6,$7,'confirmed',$6,$6)""",
            [
                (
                    incident_a,
                    org_a,
                    volunteer_membership_a,
                    volunteer,
                    "incident-a",
                    now,
                    admin_membership_a,
                ),
                (
                    incident_b,
                    org_b,
                    volunteer_membership_b,
                    volunteer,
                    "incident-b",
                    now,
                    admin_membership_b,
                ),
            ],
        )
        await connection.execute(
            """INSERT INTO volunteer_restrictions
              (id, organization_id, volunteer_user_id, incident_id, scope,
               reason_category, status, starts_at, requested_by_membership_id,
               approved_by_user_id, reviewed_at, created_at, updated_at)
            VALUES ($1,$2,$3,$4,'SHELTER','safety','active',$5,$6,$7,$5,$5,$5)""",
            restriction_b,
            org_b,
            volunteer,
            incident_b,
            now,
            admin_membership_b,
            admin_b,
        )

        await connection.execute("BEGIN")
        await connection.execute("SET LOCAL ROLE strayhub_runtime")
        await connection.execute("SELECT set_config('app.current_org_id', $1, true)", str(org_a))
        assert await connection.fetchval("SELECT count(*) FROM volunteer_notes") == 1
        assert (
            await connection.fetchval("SELECT count(*) FROM volunteer_notes WHERE id = $1", note_b)
            == 0
        )
        assert await connection.fetchval("SELECT count(*) FROM volunteer_incidents") == 1
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM volunteer_incidents WHERE id = $1", incident_b
            )
            == 0
        )
        assert await connection.fetchval("SELECT count(*) FROM volunteer_restrictions") == 0
        assert await connection.fetchval("SELECT surname FROM volunteer_profiles") == "黃"
        await connection.execute("ROLLBACK")
    finally:
        await connection.execute("DELETE FROM volunteer_restrictions WHERE id = $1", restriction_b)
        await connection.execute(
            "DELETE FROM volunteer_incidents WHERE id = ANY($1::uuid[])", [incident_a, incident_b]
        )
        await connection.execute(
            "DELETE FROM volunteer_notes WHERE id = ANY($1::uuid[])", [note_a, note_b]
        )
        await connection.execute("DELETE FROM volunteer_profiles WHERE user_id = $1", volunteer)
        await connection.execute(
            "DELETE FROM organization_memberships WHERE organization_id = ANY($1::uuid[])",
            [org_a, org_b],
        )
        await connection.execute(
            "DELETE FROM organization_volunteer_number_counters "
            "WHERE organization_id = ANY($1::uuid[])",
            [org_a, org_b],
        )
        await connection.execute(
            "DELETE FROM users WHERE id = ANY($1::uuid[])", [admin_a, admin_b, volunteer]
        )
        await connection.execute(
            "DELETE FROM organizations WHERE id = ANY($1::uuid[])", [org_a, org_b]
        )
        await connection.close()
