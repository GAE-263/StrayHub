# Phase 8 production compatibility review

Status at implementation review: deployment pending. The operator authorized compatibility review,
the necessary PR/CI/publication work and a production deployment. This is not authorization to
rewrite immutable artifacts, change IAM/WIF, operate LINE, restore production data or induce a new
rollback outage drill.

## Why a new artifact is necessary

Phase 8 candidate `6633083a2dcb0b6d87cec335b56b4a535abe2f98` was published with compatibility
`unknown`. It remains unchanged. The reviewed successor must pass new main CI, build/hosted staging
and exact-artifact publication before promotion. It must not reuse `6633083…` staging evidence.

The accepted live predecessor is `4a4761592bbab52a0e1234ef5f9ae3d92452b96d`, release
`20260916T001858Z-4a4761592bba`, manifest SHA-256
`918fcdda9e3093ce3d2fc13c57c1db9af21d83e68df4fccf90f27db2f4742185`, revision
`0056_line_webhook_auth_scope`. Read-only VM inspection confirmed that identity, its successful
roll-forward receipt and absence of an unresolved active deployment marker.

## Reviewed differences and proof boundaries

Relative to the predecessor, Phase 8 changed docs/tests, removed the one-pair source declaration,
and changed only these CI files beyond the existing deployment-tooling allowlist:

| File | Reviewed Git blob |
| --- | --- |
| `.github/workflows/ci.yml` | `2dff71b44ca2efb60c089fd5c86f7437a39483a0` |
| `.github/workflows/gce-release.yml` | `ddbd77dd6f9e8f569de892ad4d1d969960716d05` |
| `scripts/main_ci_gate.py` | `f3a54c88f401e9cb41eea449d7a12c309d0b549b` |

The workflows remove duplicate CI and use exact-main CI evidence before credentials. The new script
is a GitHub metadata reader invoked by those workflows. Although Python images copy `scripts/`,
this module is not invoked by application, worker, migration or systemd runtime paths. No app,
schema/migration, dependencies, Dockerfile, Compose, secret inventory, runtime config or LINE
implementation changed. Existing authenticated hosted acceptance still must pass for the new images.

Compatibility review schema v2 optionally binds these three specific CI paths by their exact Git
blob IDs. It does not broadly ignore `.github/` or `scripts/`. A modified blob, executable/symlink
mode or removed file fails closed; other CI/runtime paths cannot be exempted by this field. The
remaining runtime-tree comparison, exact predecessor checksum and migration gates are unchanged.
Version 1 reviews remain supported. The binding is embedded into a NEW immutable manifest; no
existing manifest or receipt is modified.

## Deployment acceptance

Require five green PR and merged-main checks, successful exact OCI hosted staging, byte-identical
publication reuse, a fresh verified GCS backup, current predecessor revalidation, and explicit
manual deployment confirmation. Use the existing canonical workflow and host lock/checkpoint logic.
After deployment require exact receipt/runtime/public health verification and matching main,
release and deployed SHA. Preserve both release directories and original receipts.

This establishes eligibility for conservative same-revision application rollback to the exact
known-good predecessor, not proof of a live rollback drill for this new pair. No migration downgrade
or automatic retry is allowed. If predecessor/CI content changes, stop and renew the review through
a PR. If deployment fails, retain checkpoint/evidence and inspect before selecting recovery.

The implementation PR timeline records final merge SHA, run IDs, artifact digests, backup ID and
deployment verification. Those results supersede the pending status of this source checkpoint.
