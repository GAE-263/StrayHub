from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.media_access import MediaAccessService
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.api.app.infrastructure.storage.ports import ObjectScope


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


@pytest.mark.asyncio
async def test_a_b_resource_matrix_hides_business_resources_and_signed_media() -> None:
    connection = await asyncpg.connect(_database_url())
    org_a, org_b = uuid4(), uuid4()
    user_a, user_b = uuid4(), uuid4()
    membership_a, membership_b = uuid4(), uuid4()
    area_a, area_b = uuid4(), uuid4()
    animal_a, animal_b = uuid4(), uuid4()
    qr_a, qr_b = uuid4(), uuid4()
    draft_a, draft_b = uuid4(), uuid4()
    media_a, media_b = uuid4(), uuid4()
    report_a, report_b = uuid4(), uuid4()
    job_a, job_b = uuid4(), uuid4()
    category_a, category_b = uuid4(), uuid4()
    option_a, option_b = uuid4(), uuid4()
    audit_a, audit_b = uuid4(), uuid4()
    medical_a, medical_b = uuid4(), uuid4()
    medical_media_a, medical_media_b = uuid4(), uuid4()
    series_a, series_b = uuid4(), uuid4()
    lineage_a, lineage_b = uuid4(), uuid4()
    occurrence_a, occurrence_b = uuid4(), uuid4()
    action_a, action_b = uuid4(), uuid4()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    answers = json.dumps({"feeding": "feeding.normal"})
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Matrix A', $2, 'active', now(), now()),
                   ($3, 'Matrix B', $4, 'active', now(), now())
            """,
            org_a,
            f"MATRIX-A-{org_a.hex[:8]}",
            org_b,
            f"MATRIX-B-{org_b.hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Matrix A', 'active', now(), now()),
                   ($3, $4, 'Matrix B', 'active', now(), now())
            """,
            user_a,
            f"matrix-a-{user_a.hex[:8]}",
            user_b,
            f"matrix-b-{user_b.hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO organization_memberships
                (id, organization_id, user_id, role, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'STAFF', 'active', now(), now()),
                   ($4, $5, $6, 'STAFF', 'active', now(), now())
            """,
            membership_a,
            org_a,
            user_a,
            membership_b,
            org_b,
            user_b,
        )
        await connection.execute(
            """
            INSERT INTO shelter_areas
                (id, organization_id, name, area_type, status, created_at, updated_at)
            VALUES ($1, $2, 'Matrix Cage A', 'cage', 'active', now(), now()),
                   ($3, $4, 'Matrix Cage B', 'cage', 'active', now(), now())
            """,
            area_a,
            org_a,
            area_b,
            org_b,
        )
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, shelter_number, area_id, status, created_at, updated_at)
            VALUES ($1, $2, 'Matrix Animal A', 'MATRIX-SAME', $3, 'active', now(), now()),
                   ($4, $5, 'Matrix Animal B', 'MATRIX-SAME', $6, 'active', now(), now())
            """,
            animal_a,
            org_a,
            area_a,
            animal_b,
            org_b,
            area_b,
        )
        await connection.execute(
            """
            INSERT INTO animal_qr_codes
                (id, organization_id, animal_id, token_digest, status, revoked,
                 created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'active', false, now(), now()),
                   ($5, $6, $7, $8, 'active', false, now(), now())
            """,
            qr_a,
            org_a,
            animal_a,
            hashlib.sha256(b"matrix-qr-a").hexdigest(),
            qr_b,
            org_b,
            animal_b,
            hashlib.sha256(b"matrix-qr-b").hexdigest(),
        )
        for draft_id, org_id, user_id, membership_id, animal_id in (
            (draft_a, org_a, user_a, membership_a, animal_a),
            (draft_b, org_b, user_b, membership_b, animal_b),
        ):
            await connection.execute(
                """
                INSERT INTO care_report_drafts
                    (id, opaque_token_digest, organization_id, volunteer_user_id, membership_id,
                     animal_id, current_step, answers, reconfirmation_keys, note, status,
                     last_interaction_at, expires_at, created_at, updated_at,
                     answer_validation_version, modification_summary)
                VALUES ($1, $2, $3, $4, $5, $6, 'answering_completion', $7::jsonb, '[]',
                        NULL, 'active', $8, $9, $8, $8, 'v1', '{}'::jsonb)
                """,
                draft_id,
                hashlib.sha256(str(draft_id).encode()).hexdigest(),
                org_id,
                user_id,
                membership_id,
                animal_id,
                answers,
                now,
                now + timedelta(days=1),
            )
        for media_id, org_id in ((media_a, org_a), (media_b, org_b)):
            await connection.execute(
                """
                INSERT INTO media_assets
                    (id, organization_id, object_key, content_type, checksum, status,
                     exif_removed, created_at, updated_at)
                VALUES ($1, $2, $3, 'image/jpeg', $4, 'processed', true, now(), now())
                """,
                media_id,
                org_id,
                f"matrix/{org_id}/photo.jpg",
                hashlib.sha256(str(media_id).encode()).hexdigest(),
            )
        for report_id, org_id, user_id, membership_id, animal_id in (
            (report_a, org_a, user_a, membership_a, animal_a),
            (report_b, org_b, user_b, membership_b, animal_b),
        ):
            await connection.execute(
                """
                INSERT INTO care_reports
                    (id, organization_id, draft_id, animal_id, volunteer_user_id, membership_id,
                     answers, animal_name_snapshot, status, ai_job_status, submitted_at,
                     created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, 'Matrix Animal', 'saved',
                        'pending_enqueue', $8, $8, $8)
                """,
                report_id,
                org_id,
                draft_id if org_id == org_a else None,
                animal_id,
                user_id,
                membership_id,
                answers,
                now,
            )
        await connection.execute(
            """
            INSERT INTO ai_processing_jobs
                (id, organization_id, job_type, target_type, target_id, status, provider,
                 model_name, model_version, prompt_template_id, prompt_version,
                 output_schema_version, created_at, updated_at)
            VALUES ($1, $2, 'care_observation', 'care_report', $3, 'pending_enqueue',
                    'mock', 'local', 'v1', 'care', 'v1', 'v1', now(), now()),
                   ($4, $5, 'care_observation', 'care_report', $6, 'pending_enqueue',
                    'mock', 'local', 'v1', 'care', 'v1', 'v1', now(), now())
            """,
            job_a,
            org_a,
            report_a,
            job_b,
            org_b,
            report_b,
        )
        await connection.execute(
            """
            INSERT INTO observation_categories
                (id, organization_id, code, display_name, description, status,
                 display_order, created_at, updated_at)
            VALUES ($1, $2, 'matrix', 'Matrix', '', 'active', 0, now(), now()),
                   ($3, $4, 'matrix', 'Matrix', '', 'active', 0, now(), now())
            """,
            category_a,
            org_a,
            category_b,
            org_b,
        )
        await connection.execute(
            """
            INSERT INTO observation_options
                (id, category_id, organization_id, code, display_name, description,
                 status, display_order, requires_note, created_at, updated_at)
            VALUES ($1, $2, $3, 'matrix.option', 'A', '', 'active', 0, false, now(), now()),
                   ($4, $5, $6, 'matrix.option', 'B', '', 'active', 0, false, now(), now())
            """,
            option_a,
            category_a,
            org_a,
            option_b,
            category_b,
            org_b,
        )
        await connection.execute(
            """
            INSERT INTO audit_records
                (id, organization_id, actor_user_id, action, resource_type, resource_id,
                 source_channel, actor_type, created_at)
            VALUES ($1, $2, $3, 'matrix', 'animal', $4, 'test', 'user', now()),
                   ($5, $6, $7, 'matrix', 'animal', $8, 'test', 'user', now())
            """,
            audit_a,
            org_a,
            user_a,
            animal_a,
            audit_b,
            org_b,
            user_b,
            animal_b,
        )
        for values in (
            (medical_a, org_a, animal_a, user_a),
            (medical_b, org_b, animal_b, user_b),
        ):
            await connection.execute(
                """
                INSERT INTO medical_records
                    (id, organization_id, animal_id, occurred_at, occurred_timezone,
                     record_type, title, content, status, version, created_by_user_id,
                     updated_by_user_id, created_at, updated_at)
                VALUES ($1, $2, $3, now(), 'Asia/Taipei', 'visit', 'Matrix medical',
                        'tenant scoped', 'active', 1, $4, $4, now(), now())
                """,
                *values,
            )
        for values in (
            (medical_media_a, org_a, medical_a, media_a, user_a),
            (medical_media_b, org_b, medical_b, media_b, user_b),
        ):
            await connection.execute(
                """
                INSERT INTO medical_record_media
                    (id, organization_id, medical_record_id, media_asset_id,
                     attached_by_user_id, attached_at)
                VALUES ($1, $2, $3, $4, $5, now())
                """,
                *values,
            )
        for values in (
            (series_a, lineage_a, org_a, animal_a, user_a),
            (series_b, lineage_b, org_b, animal_b, user_b),
        ):
            await connection.execute(
                """
                INSERT INTO care_reminder_series
                    (id, lineage_id, organization_id, animal_id, reminder_type, title,
                     anchor_local_date, anchor_local_time, frequency, created_by_user_id,
                     updated_by_user_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, 'follow_up', 'Matrix reminder', current_date,
                        '09:00', 'none', $5, $5, now(), now())
                """,
                *values,
            )
        for values in (
            (occurrence_a, org_a, lineage_a, series_a, user_a),
            (occurrence_b, org_b, lineage_b, series_b, user_b),
        ):
            await connection.execute(
                """
                INSERT INTO care_reminder_occurrences
                    (id, organization_id, lineage_id, series_id, occurrence_index,
                     nominal_local_date, nominal_local_time, original_scheduled_at,
                     scheduled_at, effective_timezone, timezone_version, title_snapshot,
                     type_snapshot, last_action_by_user_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, 0, current_date, '09:00', now(), now(),
                        'Asia/Taipei', 1, 'Matrix reminder', 'follow_up', $5, now(), now())
                """,
                *values,
            )
        for values in (
            (action_a, org_a, occurrence_a, lineage_a, series_a, user_a, str(action_a)),
            (action_b, org_b, occurrence_b, lineage_b, series_b, user_b, str(action_b)),
        ):
            await connection.execute(
                """
                INSERT INTO care_reminder_actions
                    (id, organization_id, occurrence_id, lineage_id, series_id,
                     occurrence_index, action_type, actor_user_id, acted_at,
                     idempotency_key, request_fingerprint)
                VALUES ($1, $2, $3, $4, $5, 0, 'created_override', $6, now(),
                        $7, repeat('a', 64))
                """,
                *values,
            )
        await connection.execute("SET ROLE strayhub_runtime")
        await connection.execute("SELECT set_config('app.current_org_id', $1, true)", str(org_a))
        await connection.execute("SELECT set_config('app.auth_user_id', $1, true)", str(user_a))
        checks = (
            ("organizations", org_b),
            ("organization_memberships", membership_b),
            ("animals", animal_b),
            ("animal_qr_codes", qr_b),
            ("care_report_drafts", draft_b),
            ("media_assets", media_b),
            ("care_reports", report_b),
            ("ai_processing_jobs", job_b),
            ("observation_options", option_b),
            ("audit_records", audit_b),
            ("medical_records", medical_b),
            ("medical_record_media", medical_media_b),
            ("care_reminder_series", series_b),
            ("care_reminder_occurrences", occurrence_b),
            ("care_reminder_actions", action_b),
        )
        for table, value in checks:
            id_column = "id"
            assert (
                await connection.fetchrow(
                    f"SELECT {id_column} FROM {table} WHERE {id_column} = $1", value
                )
                is None
            ), table
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM animals WHERE shelter_number = 'MATRIX-SAME'"
            )
            == 1
        )
        storage = InMemoryStorageFake()
        await storage.put(
            scope=ObjectScope(org_b),
            key="matrix/b/photo.jpg",
            data=b"clean",
            metadata=storage.metadata_for(b"clean", content_type="image/jpeg", checksum="b" * 64),
        )
        with pytest.raises(DomainError, match="照片不存在"):
            await MediaAccessService(storage, org_a).signed_url(
                media_organization_id=org_b, object_key="matrix/b/photo.jpg"
            )
        await connection.execute("ROLLBACK")
    finally:
        await connection.close()
