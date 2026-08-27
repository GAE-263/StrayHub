"""Preview/delete only known local test fixtures, using the live PostgreSQL FK graph."""

import argparse
import asyncio
import json
from graphlib import TopologicalSorter

from scripts.local_demo import guard
from services.api.app.persistence.database.engine import engine
from sqlalchemy import MetaData, and_, delete, select, text, tuple_

LEGACY_CODES = ("ORG-A", "ORG-B", "ORG-DISABLED")


def fixture_usernames() -> set[str]:
    names = {"local-platform-admin", "local-platform-admin-disabled"}
    for suffix in ("a", "b"):
        names.update(
            f"{prefix}-{suffix}"
            for prefix in (
                "local-staff",
                "local-volunteer",
                "local-shelter-admin",
                "medical-staff-denied",
                "medical-volunteer-unassigned",
            )
        )
    names.update(
        f"local-volunteer-state-{state}"
        for state in ("rejected", "future", "expired", "revoked", "disabled_user")
    )
    for prefix, count in (("manual", 100), ("all-filtered", 1200)):
        names.update(f"local-applicant-{prefix}-{i:04d}" for i in range(1, count + 1))
    return names


def selected(table, keys):
    return tuple_(*table.primary_key.columns).in_(list(keys))


async def plan_cleanup(conn):
    metadata = MetaData()
    await conn.run_sync(lambda sync: metadata.reflect(sync, schema="public"))
    tables = {t.name: t for t in metadata.tables.values()}
    foreign_keys = [fk for t in tables.values() for fk in t.foreign_key_constraints]
    org = tables["organizations"]
    org_ids = set((await conn.scalars(select(org.c.id).where(org.c.code.in_(LEGACY_CODES)))).all())
    keys = {name: set() for name in tables}
    keys["organizations"] = {(oid,) for oid in org_ids}

    async def descendants():
        changed = True
        while changed:
            changed = False
            for fk in foreign_keys:
                parent, child = fk.referred_table, fk.table
                if not keys[parent.name]:
                    continue
                # Aliasing also handles self-references without ambiguous SQL.
                parent_alias = parent.alias()
                match = and_(*(e.parent == parent_alias.c[e.column.name] for e in fk.elements))
                scope_column = child.c.get("organization_id")
                if scope_column is None:
                    scope_column = child.c.get("active_organization_id")
                columns = list(child.primary_key.columns)
                if not columns:
                    raise RuntimeError(f"unsupported_cleanup_key:{child.name}")
                if scope_column is not None:
                    columns.append(scope_column)
                rows = (
                    await conn.execute(
                        select(*columns)
                        .select_from(child.join(parent_alias, match))
                        .where(
                            tuple_(
                                *(parent_alias.c[c.name] for c in parent.primary_key.columns)
                            ).in_(list(keys[parent.name]))
                        )
                    )
                ).all()
                found = set()
                for row in rows:
                    if scope_column is not None:
                        scope = row[-1]
                        # Null active context is an identity row, not tenant data.
                        if scope not in org_ids and not (
                            scope is None and scope_column.name == "active_organization_id"
                        ):
                            raise RuntimeError(f"cross_tenant_reference:{child.name}")
                        row = row[:-1]
                    found.add(tuple(row))
                if found - keys[child.name]:
                    keys[child.name].update(found)
                    changed = True

    await descendants()
    users = tables["users"]
    candidates = set(
        (
            await conn.scalars(select(users.c.id).where(users.c.username.in_(fixture_usernames())))
        ).all()
    )
    blocked = set()
    # A known test user who acquired retained history/access must not be removed.
    for fk in foreign_keys:
        if fk.referred_table.name != "users":
            continue
        child = fk.table
        column = next(iter(fk.elements)).parent
        query = select(column).where(column.in_(candidates), ~selected(child, keys[child.name]))
        if child.name == "session_records":
            query = query.where(
                child.c.active_organization_id.is_not(None),
                ~child.c.active_organization_id.in_(org_ids),
            )
        elif child.name == "line_user_bindings":
            continue
        blocked.update((await conn.scalars(query)).all())
    bindings = tables["line_user_bindings"]
    for fk in foreign_keys:
        if fk.referred_table.name == "line_user_bindings":
            child = fk.table
            match = and_(*(e.parent == e.column for e in fk.elements))
            blocked.update(
                (
                    await conn.scalars(
                        select(bindings.c.user_id)
                        .select_from(child.join(bindings, match))
                        .where(
                            bindings.c.user_id.in_(candidates), ~selected(child, keys[child.name])
                        )
                    )
                ).all()
            )
    keys["users"] = {(uid,) for uid in candidates - blocked}
    await descendants()
    graph = {name: set() for name, rows in keys.items() if rows}
    for fk in foreign_keys:
        child, parent = fk.table.name, fk.referred_table.name
        if child in graph and parent in graph and child != parent:
            graph[child].add(parent)
    order = list(reversed(tuple(TopologicalSorter(graph).static_order())))
    return tables, keys, order, len(blocked)


async def cleanup(*, apply=False):
    guard()
    async with engine.begin() as conn:
        if not await conn.scalar(
            text("SELECT has_table_privilege(current_user,'public.users','DELETE')")
        ):
            raise RuntimeError(
                "operator_cleanup_credentials_required: never grant DELETE to runtime"
            )
        # Serialize plans and lock tables for --yes so FK/row changes cannot race
        # the previewed selection. Read-only default never deletes or locks writers.
        if apply:
            await conn.execute(text("SET LOCAL lock_timeout='5s'"))
            await conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('local-demo-cleanup'))"))
            names = (
                await conn.scalars(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                        "ORDER BY tablename"
                    )
                )
            ).all()
            quote = conn.dialect.identifier_preparer.quote
            await conn.execute(
                text(
                    "LOCK TABLE "
                    + ",".join("public." + quote(n) for n in names)
                    + " IN SHARE ROW EXCLUSIVE MODE"
                )
            )
        else:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
        tables, keys, order, retained_users = await plan_cleanup(conn)
        summary = {
            "target_codes": list(LEGACY_CODES),
            "delete_counts": {name: len(keys[name]) for name in order},
            "retained_referenced_fixture_users": retained_users,
            "applied": apply,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        if apply:
            for name in order:
                await conn.execute(delete(tables[name]).where(selected(tables[name], keys[name])))
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Apply the exact fixture deletion; default is read-only preview",
    )
    args = parser.parse_args()
    try:
        asyncio.run(cleanup(apply=args.yes))
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
