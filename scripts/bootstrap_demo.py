"""Three-shelter local data bootstrap; never invokes test fixtures or deletes data."""

import argparse
import asyncio
import json

from scripts.import_moa_shelter_animals import run as import_moa
from scripts.local_demo import DEMO_SHELTERS, guard
from scripts.seed_demo_accounts import seed as seed_accounts
from scripts.seed_furkids_demo import seed as seed_furkids
from scripts.verify_demo_data import verify, verify_shelter


async def import_or_reuse(
    code,
    *,
    refresh=False,
    run_import=None,
    verify=None,
    limit=60,
):
    if run_import is None:

        async def run_import(**kwargs):
            return await import_moa(argparse.Namespace(**kwargs))

    if verify is None:

        async def verify(code):
            return await verify_shelter(code, photos=True)

    existing = await verify(code)
    shelter_name = DEMO_SHELTERS[code]
    if existing["valid"] and not refresh:
        print(
            f"[Demo] {shelter_name}: reuse verified local dataset "
            f"({existing['animals']} animals, photos valid)",
            flush=True,
        )
        return {"sync": "reused_existing", **existing}

    if refresh:
        print(f"[Demo] {shelter_name}: forced live MOA refresh", flush=True)
    else:
        print(
            f"[Demo] {shelter_name}: local dataset unavailable; performing live MOA sync",
            flush=True,
        )

    import_error = None
    try:
        result = await run_import(
            shelter=shelter_name,
            kind="dog",
            limit=limit,
            dry_run=False,
        )
    except Exception as exc:  # pragma: no cover - importer normally returns an exit code
        import_error = exc
        result = 1

    verified = await verify(code)
    if result != 0:
        if refresh:
            availability = (
                "existing verified data still available"
                if verified["valid"]
                else "no valid local dataset available"
            )
            print(
                f"[Demo] ERROR {shelter_name}: refresh failed; {availability}",
                flush=True,
            )
            error = RuntimeError(f"refresh_failed:{code}")
            if import_error is not None:
                raise error from import_error
            raise error
        if not verified["valid"]:
            raise RuntimeError(f"no_valid_local_dataset:{code}") from import_error
        print(
            f"[Demo] WARNING {shelter_name}: live sync failed/incomplete; "
            f"repair left a verified local dataset ({verified['animals']} animals), "
            "NOT a successful fresh sync.",
            flush=True,
        )
        return {"sync": "repaired_existing", **verified}

    if not verified["valid"]:
        raise RuntimeError(f"no_valid_local_dataset:{code}")
    return {"sync": "completed", **verified}


async def bootstrap(*, refresh=False):
    guard(storage=True)
    print(
        "[Demo] FurKids: seed 5 animals and approved photos (reuse valid local bytes)", flush=True
    )
    await seed_furkids()
    sync = {}
    for code in ("MOA-SHELTER-51", "MOA-SHELTER-58"):
        sync[code] = await import_or_reuse(code, refresh=refresh)
    print(
        "[Demo] Shared vocabulary, minimum demo accounts, and three volunteer policies",
        flush=True,
    )
    await seed_accounts()
    return {"sync": sync, "verified": await verify(photos=True)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="force the latest official MOA sync before final verification",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(bootstrap(refresh=args.refresh)),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
