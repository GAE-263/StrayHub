# CI/CD Phase 7 live acceptance record

Status: PASS. Deployment, same-artifact resume, rollback, roll-forward and final independent
verify-only all passed on 2026-09-16. Production finishes on `4a476159…`.
All timestamps below are UTC. This is historical evidence, not permission for future operations.

## Reviewed scope

The operator authorized production deployment and controlled recovery/rollback acceptance, then
approved a follow-up exact-predecessor compatibility declaration. No IAM/WIF changes, schema
downgrade, production data restore or modification of published artifacts is included.

- Base checkpoint/resume protections: [PR #42](https://github.com/GAE-263/StrayHub/pull/42).
- Exact predecessor compatibility: [PR #43](https://github.com/GAE-263/StrayHub/pull/43).
- Accepted predecessor: `7bb29ea60aeee435b0f05744af969a2ce0542882`, release
  `20260915T154252Z-7bb29ea60aee`.
- Predecessor manifest SHA-256:
  `6e7584eebfb08c579f8c944423539684e3144d3c44eeda5ef7877058e07080ff`.
- Candidate: `4a4761592bbab52a0e1234ef5f9ae3d92452b96d`, release
  `20260916T001858Z-4a4761592bba`.
- Both migration revisions: `0056_line_webhook_auth_scope`.

Production readback confirmed the exact predecessor manifest and successful receipt. The new
builder compared tracked runtime blob identities and embedded the exact predecessor binding into
a new manifest. Application, migrations, dependencies and runtime configuration did not change.
The earlier `f70f9b5…` Phase 7 artifact remains `unknown` and is not this deployment candidate.

## CI and hosted staging

| Evidence | Result | Run |
| --- | --- | --- |
| PR #43 final CI | All five checks PASS | [35038988819](https://github.com/GAE-263/StrayHub/actions/runs/35038988819) |
| Merged main CI | PASS | [35039483033](https://github.com/GAE-263/StrayHub/actions/runs/35039483033) |
| Immutable build and hosted Docker staging | Both PASS | [35039483024](https://github.com/GAE-263/StrayHub/actions/runs/35039483024) |
| Release fast-forward push CI | PASS; deploy skipped | [35039968429](https://github.com/GAE-263/StrayHub/actions/runs/35039968429) |
| Publication | PASS; canonical artifact reused | [35039988875](https://github.com/GAE-263/StrayHub/actions/runs/35039988875) |
| Production deploy and independent post-verification | Both PASS | [35040950207](https://github.com/GAE-263/StrayHub/actions/runs/35040950207) |
| Final independent verify-only after rollback/roll-forward | PASS; publish/deploy skipped | [35043260223](https://github.com/GAE-263/StrayHub/actions/runs/35043260223) |

Local complete test suite: 2,758 passed, two data-dependent tests skipped. The initial PR CI found
five simulated-registry tests depending on unavailable production Git history in a shallow test
checkout. The fixture now uses a synthetic same-tree predecessor; a separate negative test proves
missing predecessor history still fails closed. Production build checkout retains full history.
The final PR CI passed without weakening that check.

Candidate identity:

- OCI digest: `sha256:26e701ca4d2730edac6c45255469f36e2f9dd820086f706ede10d56d91b73ec8`.
- Manifest SHA-256: `918fcdda9e3093ce3d2fc13c57c1db9af21d83e68df4fccf90f27db2f4742185`.
- Bundle SHA-256: `63f3b4834e39cc12f2b79d1951866ea7d39487bd2a156453931e3afcb67fbaf2`.
- API: `sha256:c00b178504e8db848053cf7641e9a49667fea6695671327e12abbc746d31be9c`.
- Web: `sha256:5d60053822a0c5e3db9b37fd7491c06a7bfcb85008a297cea2e61b4589931166`.
- Worker: `sha256:a04c5ccf9d477c6391bc3e30f004aee3824eda1a768cade96a457f0213cd81c2`.
- Staging run attempt: `1`; artifact ID: `10424976034`.
- Staging archive SHA-256: `e49235be5fa28a7b2fdb614157748818c2198af62f5d4f43db561d7421d787d1`.

The staging gate verified the downloaded archive against live run/artifact metadata and the exact
candidate manifest, bundle and image identities. Authenticated login, cross-shelter denial, RLS
(48 tables), non-superuser/non-BYPASSRLS runtime role and application acceptance all passed in the
disposable hosted Docker environment. This is not a claim of authenticated production data testing.

Publication artifact ID: `10424623089`; archive SHA-256:
`f58bed9691ef8c21db1b48856e4082fff85a5495ec884c261959abd06744801c`.
The publication manifest was byte-identical to the hosted build manifest. Artifact validation,
publication receipt validation and the full live staging evidence gate passed before deployment.

## Fresh backup

Standard production backup service completed successfully at `2026-09-16T00:06:11Z`:

```text
20260916T000427Z-e3daily10889
gs://strayhub-backups-canvas-primacy-502703-k1/strayhub-backups/production/20260916T000427Z-e3daily10889/
```

Canonical preflight/upload reported PASS (including download/checksum verification before marker
publication); the GCS `_COMPLETE` marker was read back and matched this backup ID. No production
database or MinIO restore was performed.

## Operational history and recovery evidence

Release advanced from `7bb29ea…` to `4a476159…` by normal fast-forward, not force push. A publication
dispatch with an incorrect confirmation string was canceled before publication (run
`35039967520`); the corrected fresh run is recorded above. No rerun-button attempt or gate bypass
was used.

Deployment completed with checkpoint `complete`, no active deployment marker, successful systemd
service states, exact image references and independent post-verification. The original successful
candidate receipt SHA-256 is `05ed6756e5ed2ca57a8c3bbb7c7463d12eb016cc3381c8c4cb0d24b1a69d3e03`.

Same-artifact `--resume` passed at `2026-09-16T00:55:07Z` using the validated root-owned retained
bootstrap. Container IDs, start times, image references and restart counts were identical before
and after. Main service, migration and secrets unit execution timestamps were unchanged. The
original receipt checksum above was unchanged; checkpoint remained complete and the active marker
was absent. The canonical resume path read the live DB head and verified runtime/public health
without migration upgrade, image pull, secret materialization or service restart.

Controlled rollback passed at `2026-09-16T01:04:14Z`, from `4a476159…` to the exact `7bb29ea…`
predecessor. The tool reported `database downgrade: NONE`; the verified rollback receipt is
`rollback-20260916T010413Z-20260915T154252Z-7bb29ea60aee.json`. It records the old SHA/image digests,
unchanged migration revision and the newer release as its previous release. Original per-release
receipts and immutable directories were preserved.

Independent receipt/runtime verification of the old release also passed before roll-forward.
Using the retained NEW tool by its immutable absolute path, roll-forward passed at
`2026-09-16T01:13:35Z`, returning production to `4a476159…`. The tool reported `migration: NONE`.
Its receipt is `rollforward-20260916T011335Z-20260916T001858Z-4a4761592bba.json`, recording the exact
new image digests and the accepted old release as predecessor. These stop/start operations are
maintenance operations, not a zero-downtime deployment claim.

Final independent GitHub verify-only run `35043260223` passed, with publication/deployment jobs
skipped. Final host readback confirmed the exact candidate API/Web/Worker digests, successful active
main/migration/secrets units, complete checkpoint, no active deployment marker, and current receipt
pointing to the successful roll-forward receipt. The original candidate receipt and predecessor
manifest checksums remained unchanged.

No intentional production migration failure or destructive interruption was part of this drill;
ambiguity/failure paths are covered by isolated tests described in
[the recovery runbook](recovery-rollback.md). Live resume acceptance covers the completed-release
verify-only path, not an induced production crash or a database restore. Future application/schema
changes require renewed compatibility review; this acceptance does not authorize other release
pairs. Phase 8 legacy workflow/branch cleanup remains a separate task.
