"""Three-shelter local data bootstrap; never invokes test fixtures or deletes data."""

import argparse
import asyncio
import json

from scripts.import_moa_shelter_animals import run as import_moa
from scripts.local_demo import DEMO_SHELTERS, guard
from scripts.seed_demo_accounts import seed as seed_accounts
from scripts.seed_furkids_demo import seed as seed_furkids
from scripts.verify_demo_data import verify, verify_shelter


async def import_or_reuse(code, *, run_import=None, verify=None, limit=60):
    if run_import is None:

        async def run_import(**kwargs):
            return await import_moa(argparse.Namespace(**kwargs))

    if verify is None:

        async def verify(code):
            return await verify_shelter(code, photos=True)

    result = await run_import(shelter=DEMO_SHELTERS[code], kind="dog", limit=limit, dry_run=False)
    if result == 0:
        return {"sync": "completed"}
    existing = await verify(code)
    if not existing["valid"]:
        raise RuntimeError(f"no_valid_local_dataset:{code}")
    print(
        f"[Demo] WARNING {code}: live sync failed/incomplete; "
        f"reusing verified local data ({existing['animals']} animals), "
        "NOT a successful fresh sync.",
        flush=True,
    )
    return {"sync": "reused_existing", **existing}


async def bootstrap():
    guard(storage=True)
    print(
        "[Demo] FurKids: seed 5 animals and approved photos (reuse valid local bytes)", flush=True
    )
    await seed_furkids()
    sync = {}
    for code in ("MOA-SHELTER-51", "MOA-SHELTER-58"):
        print(
            f"[Demo] {DEMO_SHELTERS[code]}: live dog import, up to 60; "
            "first photo download may take several minutes",
            flush=True,
        )
        sync[code] = await import_or_reuse(code)
    print("[Demo] Shared vocabulary and minimum demo accounts", flush=True)
    await seed_accounts()
    return {"sync": sync, "verified": await verify(photos=True)}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(bootstrap()), ensure_ascii=False, indent=2))
