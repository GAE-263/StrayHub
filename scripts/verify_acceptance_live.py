"""Run authenticated E5 acceptance against deterministic synthetic fixtures."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from uuid import UUID

import httpx
from scripts.bootstrap_acceptance import (
    ANIMAL_A_NUMBER,
    ANIMAL_B_NUMBER,
    CONFIRMATION_ENV,
    TENANT_A_CODE,
    TENANT_B_CODE,
    VOLUNTEER_A_USERNAME,
    read_bootstrap_password,
    validate_execution_guard,
)

ANSWERS = {
    "care_completion": "care_completion.completed",
    "walk_completion": "walk_completion.not_done",
    "feeding": "feeding.not_observed",
    "water": "water.not_observed",
    "activity": "activity.not_observed",
    "urination": "urination.not_observed",
    "defecation": "defecation.not_observed",
    "resource_guarding": "resource_guarding.not_observed",
    "human_interaction": "human_interaction.uncertain",
    "animal_interaction": "animal_interaction.uncertain",
    "emotion": "emotion.not_observed",
    "walk_reaction": "walk.not_observed",
    "appearance_special_status": "appearance.not_observed",
}


def _require(response: httpx.Response, *expected: int) -> dict:
    if response.status_code not in expected:
        raise RuntimeError(
            f"acceptance_http_failure: {response.request.method} "
            f"{response.request.url.path} returned {response.status_code}"
        )
    if not response.content:
        return {}
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("acceptance_http_failure: expected object response")
    return payload


async def _fixture_inventory() -> dict:
    from services.api.app.application.qr_token_service import printable_token_for
    from services.api.app.config.settings import Settings
    from services.api.app.persistence.database.scope import (
        set_organization_scope,
        set_platform_scope,
    )
    from services.api.app.persistence.models.animal import Animal
    from services.api.app.persistence.models.identity import Organization
    from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    settings = Settings().validate_runtime_safety(process="api")
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            await set_platform_scope(session)
            organizations = list(
                (
                    await session.scalars(
                        select(Organization).where(
                            Organization.code.in_([TENANT_A_CODE, TENANT_B_CODE])
                        )
                    )
                ).all()
            )
            by_code = {organization.code: organization for organization in organizations}
            if set(by_code) != {TENANT_A_CODE, TENANT_B_CODE}:
                raise RuntimeError("acceptance_fixture_inventory_missing_tenants")

            animals: dict[str, Animal] = {}
            raw_qr: dict[str, str] = {}
            for code, shelter_number in (
                (TENANT_A_CODE, ANIMAL_A_NUMBER),
                (TENANT_B_CODE, ANIMAL_B_NUMBER),
            ):
                organization = by_code[code]
                await set_organization_scope(session, organization.id)
                animal = await session.scalar(
                    select(Animal).where(
                        Animal.organization_id == organization.id,
                        Animal.shelter_number == shelter_number,
                    )
                )
                if animal is None:
                    raise RuntimeError(f"acceptance_fixture_inventory_missing_animal: {code}")
                active_qr = await QrCodeRepository(session, organization.id).active_for_animal(
                    animal.id
                )
                if active_qr is None:
                    raise RuntimeError(f"acceptance_fixture_inventory_missing_qr: {code}")
                animals[code] = animal
                raw_qr[code] = printable_token_for(active_qr)

            runtime_role = (
                await session.execute(
                    text(
                        "SELECT rolname, rolbypassrls, rolsuper FROM pg_roles "
                        "WHERE rolname = 'strayhub_app'"
                    )
                )
            ).one()
            rls_table_count = await session.scalar(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relrowsecurity"
                )
            )
            return {
                "tenant_a_id": by_code[TENANT_A_CODE].id,
                "tenant_b_id": by_code[TENANT_B_CODE].id,
                "animal_a_id": animals[TENANT_A_CODE].id,
                "animal_b_id": animals[TENANT_B_CODE].id,
                "qr_a": raw_qr[TENANT_A_CODE],
                "qr_b": raw_qr[TENANT_B_CODE],
                "runtime_role": runtime_role.rolname,
                "runtime_bypassrls": runtime_role.rolbypassrls,
                "runtime_superuser": runtime_role.rolsuper,
                "rls_table_count": int(rls_table_count or 0),
            }
    finally:
        await engine.dispose()


async def verify_live(*, base_url: str, password: str) -> dict:
    fixtures = await _fixture_inventory()
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0, follow_redirects=False) as client:
        invalid = await client.get("/v1/auth/me")
        if invalid.status_code != 401:
            raise RuntimeError(f"acceptance_invalid_auth_expected_401: {invalid.status_code}")

        login = _require(
            await client.post(
                "/v1/auth/login",
                json={"username": VOLUNTEER_A_USERNAME, "password": password},
            ),
            200,
        )
        access_token = login.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("acceptance_login_missing_access_token")
        headers = {"Authorization": f"Bearer {access_token}"}

        selected = _require(
            await client.put(
                "/v1/auth/active-shelter-context",
                headers=headers,
                json={"organization_id": str(fixtures["tenant_a_id"])},
            ),
            200,
        )
        if UUID(selected["organization_id"]) != fixtures["tenant_a_id"]:
            raise RuntimeError("acceptance_tenant_a_context_mismatch")

        me = _require(await client.get("/v1/auth/me", headers=headers), 200)
        membership_orgs = {
            UUID(item["organization_id"])
            for item in me.get("memberships", [])
            if item.get("status") == "active"
        }
        if membership_orgs != {fixtures["tenant_a_id"]}:
            raise RuntimeError("acceptance_membership_scope_mismatch")

        animals = _require(await client.get("/v1/animals", headers=headers), 200)
        animal_ids = {UUID(item["id"]) for item in animals.get("items", [])}
        if fixtures["animal_a_id"] not in animal_ids or fixtures["animal_b_id"] in animal_ids:
            raise RuntimeError("acceptance_tenant_a_animal_scope_mismatch")

        tenant_b_switch = await client.put(
            "/v1/auth/active-shelter-context",
            headers=headers,
            json={"organization_id": str(fixtures["tenant_b_id"])},
        )
        if tenant_b_switch.status_code not in {403, 404}:
            raise RuntimeError(
                f"acceptance_cross_tenant_switch_not_denied: {tenant_b_switch.status_code}"
            )

        resolved = _require(
            await client.post(
                "/v1/qr-tokens/resolve",
                headers=headers,
                json={"qr_token": fixtures["qr_a"]},
            ),
            200,
        )
        if UUID(resolved["id"]) != fixtures["animal_a_id"]:
            raise RuntimeError("acceptance_qr_a_resolution_mismatch")

        confirmed = _require(
            await client.post(f"/v1/animals/{fixtures['animal_a_id']}/confirm", headers=headers),
            200,
        )
        confirmation_token = confirmed.get("confirmation_token")
        if not isinstance(confirmation_token, str) or not confirmation_token:
            raise RuntimeError("acceptance_confirmation_token_missing")

        draft = _require(
            await client.post(
                "/v1/care-report-drafts",
                headers=headers,
                json={
                    "animal_id": str(fixtures["animal_a_id"]),
                    "confirmation_token": confirmation_token,
                },
            ),
            201,
        )
        report = _require(
            await client.post(
                "/v1/care-reports",
                headers={**headers, "Idempotency-Key": "e5b-live-acceptance-20260830-v1"},
                json={
                    "draft_id": draft["id"],
                    "observations": ANSWERS,
                    "note": "Synthetic E5b live acceptance only",
                    "media_ids": [],
                },
            ),
            201,
        )
        if UUID(report["organization_id"]) != fixtures["tenant_a_id"]:
            raise RuntimeError("acceptance_report_tenant_mismatch")

        cross_shelter = await client.post(
            "/v1/qr-tokens/candidate-organization",
            headers=headers,
            json={
                "qr_token": fixtures["qr_b"],
                "candidate_organization_id": str(fixtures["tenant_b_id"]),
            },
        )
        if cross_shelter.status_code not in {403, 404}:
            raise RuntimeError(f"acceptance_cross_shelter_not_denied: {cross_shelter.status_code}")

    return {
        "valid_login": "PASS",
        "invalid_auth": "PASS (401)",
        "authenticated_api": "PASS",
        "tenant_a_positive": "PASS",
        "tenant_b_negative": f"PASS ({tenant_b_switch.status_code})",
        "volunteer_grant": "PASS",
        "qr_first": "PASS",
        "care_report": "PASS",
        "care_report_id": report["id"],
        "cross_shelter_denial": f"PASS ({cross_shelter.status_code})",
        "runtime_role": fixtures["runtime_role"],
        "runtime_bypassrls": fixtures["runtime_bypassrls"],
        "runtime_superuser": fixtures["runtime_superuser"],
        "rls_table_count": fixtures["rls_table_count"],
    }


async def _run(args: argparse.Namespace) -> int:
    validate_execution_guard(
        app_env=os.getenv("APP_ENV"),
        allow_value=os.getenv(CONFIRMATION_ENV),
        confirmed=args.confirm_synthetic_data,
    )
    password = read_bootstrap_password(os.environ)
    result = await verify_live(base_url=args.base_url.rstrip("/"), password=password)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--confirm-synthetic-data", action="store_true")
    raise SystemExit(asyncio.run(_run(parser.parse_args())))


if __name__ == "__main__":
    main()
