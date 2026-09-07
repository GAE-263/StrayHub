"""Operator-only, post-migration runtime ACL check/repair; never changes RLS."""

import argparse
import asyncio
import json

from services.api.app.config.settings import get_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

IDENTITY_TABLES = (
    "users",
    "session_records",
    "refresh_token_records",
    "google_user_bindings",
    "google_auth_transactions",
)
TENANT_TABLES = (
    "organizations",
    "organization_memberships",
    "audit_records",
    "animals",
    "animal_external_sources",
    "media_assets",
    "animal_qr_codes",
    "organization_invitations",
    "organization_join_applications",
)


async def configure(database_url: str, *, apply: bool = False) -> dict:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            role = (
                (
                    await connection.execute(
                        text(
                            "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb "
                            "FROM pg_roles WHERE rolname='strayhub_runtime'"
                        )
                    )
                )
                .mappings()
                .one()
            )
            if any(role.values()):
                raise RuntimeError("Runtime role must not have administrative or RLS-bypass rights")
            owner = await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner "
                    "WHERE r.rolname='strayhub_runtime' AND c.relnamespace='public'::regnamespace"
                )
            )
            if owner:
                raise RuntimeError("Runtime role must not own application schema objects")
            missing = []
            if not await connection.scalar(
                text(
                    "SELECT has_function_privilege('strayhub_runtime', "
                    "'public.join_organization(uuid)', 'EXECUTE')"
                )
            ):
                raise RuntimeError(
                    "Missing join_organization function EXECUTE grant; apply migration"
                )
            for table in IDENTITY_TABLES:
                permissions = ("SELECT", "INSERT", "UPDATE")
                if table == "google_auth_transactions":
                    permissions += ("DELETE",)
                for permission in permissions:
                    if not await connection.scalar(
                        text("SELECT has_table_privilege('strayhub_runtime',:table,:permission)"),
                        {"table": f"public.{table}", "permission": permission},
                    ):
                        missing.append(f"{table}:{permission}")
                if apply:
                    # Only expired login transactions need DELETE for cleanup.
                    # Never grant ownership, role membership or schema privileges.
                    await connection.execute(
                        text(
                            f"GRANT {', '.join(permissions)} ON public.{table} TO strayhub_runtime"
                        )
                    )
            for table in TENANT_TABLES:
                protected = await connection.scalar(
                    text(
                        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                        "WHERE oid=to_regclass(:table)"
                    ),
                    {"table": f"public.{table}"},
                )
                if not protected:
                    raise RuntimeError(f"RLS and FORCE RLS required: {table}")
                permissions = (
                    ("SELECT", "INSERT")
                    if table == "audit_records"
                    else ("SELECT", "INSERT", "UPDATE")
                    if table in {"organization_invitations", "organization_join_applications"}
                    else ("SELECT", "INSERT", "UPDATE", "DELETE")
                )
                for permission in permissions:
                    if not await connection.scalar(
                        text("SELECT has_table_privilege('strayhub_runtime',:table,:permission)"),
                        {"table": f"public.{table}", "permission": permission},
                    ):
                        raise RuntimeError(f"Missing tenant ACL: {table}:{permission}")
            return {"runtime_role": "strayhub_runtime", "missing_grants": missing, "applied": apply}
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Grant only missing identity-table DML"
    )
    args = parser.parse_args()
    result = asyncio.run(configure(get_settings().database_url, apply=args.apply))
    print(json.dumps(result))
    if result["missing_grants"] and not args.apply:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
