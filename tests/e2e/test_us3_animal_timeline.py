import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


@pytest.mark.asyncio
async def test_us3_timeline_keeps_fourteen_days_and_same_day_reports_isolated() -> None:
    connection = await asyncpg.connect(_database_url())
    organization_a = uuid4()
    organization_b = uuid4()
    animal_a = uuid4()
    animal_b = uuid4()
    user_a = uuid4()
    membership_a = uuid4()
    report_a1 = uuid4()
    report_a2 = uuid4()
    report_b = uuid4()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'US3 A', $2, 'active', now(), now()),
                   ($3, 'US3 B', $4, 'active', now(), now())
            """,
            organization_a,
            f"US3-A-{organization_a.hex[:10]}",
            organization_b,
            f"US3-B-{organization_b.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'US3 Staff A', 'active', now(), now())
            """,
            user_a,
            f"us3-staff-{user_a.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO organization_memberships
                (id, organization_id, user_id, role, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'STAFF', 'active', now(), now())
            """,
            membership_a,
            organization_a,
            user_a,
        )
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, shelter_number, status, created_at, updated_at)
            VALUES ($1, $2, 'A Timeline Animal', $3, 'active', now(), now()),
                   ($4, $5, 'B Timeline Animal', $6, 'active', now(), now())
            """,
            animal_a,
            organization_a,
            f"US3-A-{animal_a.hex[:8]}",
            animal_b,
            organization_b,
            f"US3-B-{animal_b.hex[:8]}",
        )
        answers = {
            "care_completion": "care_completion.completed",
            "walk_completion": "walk_completion.completed",
            "feeding": "feeding.normal",
            "water": "water.observed",
            "activity": "activity.usual",
            "urination": "urination.observed",
            "defecation": "defecation.formed",
            "resource_guarding": "resource_guarding.not_observed",
            "human_interaction": "human_interaction.usual",
            "animal_interaction": "animal_interaction.usual",
            "emotion": "emotion.calm",
            "walk_reaction": "walk.willing",
            "appearance_special_status": "appearance.not_observed",
        }
        for report_id, animal_id, submitted_at, volunteer_id in (
            (report_a1, animal_a, now, user_a),
            (report_a2, animal_a, now + timedelta(minutes=5), user_a),
            (report_b, animal_b, now, user_a),
        ):
            await connection.execute(
                """
                INSERT INTO care_reports
                    (id, organization_id, animal_id, volunteer_user_id, membership_id,
                     answers, animal_name_snapshot, status, ai_job_status, submitted_at,
                     created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, 'Timeline Animal', 'saved',
                        'pending_enqueue', $7, now(), now())
                """,
                report_id,
                organization_a if animal_id == animal_a else organization_b,
                animal_id,
                volunteer_id,
                membership_a,
                json.dumps(answers),
                submitted_at,
            )
        await connection.execute("SET ROLE strayhub_runtime")
        await connection.execute(
            "SELECT set_config('app.current_org_id', $1, true)", str(organization_a)
        )
        await connection.execute("SELECT set_config('app.auth_user_id', $1, true)", str(user_a))
        rows = await connection.fetch(
            """
            SELECT animal_id, count(*) AS report_count
            FROM care_reports
            WHERE animal_id IN ($1, $2)
            GROUP BY animal_id
            ORDER BY animal_id
            """,
            animal_a,
            animal_b,
        )
        assert [(row["animal_id"], row["report_count"]) for row in rows] == [(animal_a, 2)]
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM care_reports WHERE animal_id = $1", animal_b
            )
            == 0
        )
        await connection.execute("ROLLBACK")
    finally:
        await connection.close()
