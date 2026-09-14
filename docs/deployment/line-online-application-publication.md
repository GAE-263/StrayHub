# Application publication — 2026-09-14

## Authorized attempt

- Repository: GAE-263/StrayHub.
- Release: `a3e206f9a553d75be9ac342ce73998ce1cf9badc`.
- Workflow: `.github/workflows/gce-release.yml`; operation=publish, schema_compatibility=unknown.
- Confirmation: `PUBLISH a3e206f9a553d75be9ac342ce73998ce1cf9badc`.
- [Run 34862095364](https://github.com/GAE-263/StrayHub/actions/runs/34862095364): workflow_dispatch, release, attempt 1, actor/triggering_actor=yawan0203. Dispatched exactly once; no rerun/cancel or subsequent dispatch.
- Preflight verified exact source workflow/gates against the remote SHA, release/main refs, absence of prior manual runs for this SHA, and unchanged publisher WIF/Registry policies.

## Failure evidence

- Job `104036662005`, `Authorize exact manual write operation`, failed at `Refuse stale release candidates and verify manual confirmation`.
- At `2026-09-14T15:26:00.8917318Z`: `fatal: could not read Username for 'https://github.com': No such device or address`.
- Exit code 128. The step failed at git fetch before the manual gate Python invocation.
- Source uses checkout with persist-credentials=false, then runs git fetch without a separately configured Git credential. This matches the authentication failure. It is not evidence of a WIF rejection or a failed runtime application test.
- This manual-only authorization path was not exercised by successful push/PR CI. No code or workflow changes were made to bypass it.

## Recovery boundary

Do not rerun this attempt. A reviewed workflow correction and regression that covers fetch authentication are needed before a new manual dispatch. Any correction must retain exact release SHA, both actors, attempt 1, fresh authoritative release HEAD and zero writes for push/PR. If the correction changes release SHA, freeze and validate the new candidate; do not label it as this candidate.

No publication receipt or image digest can be inferred from the verification-only builds. No deployment, LINE publication, secret payload access, config sync or runtime restart was authorized or performed by this attempt.

## Final readback

Run completed with conclusion=failure. Candidate verification (including clean-SHA image build), Python, Frontend Quality, Contracts and Critical E2E all succeeded. Manual authorization failed; Publish immutable release candidate, Production deployment and Production verification were SKIPPED. Artifacts total_count=0.

Result: APPLICATION PUBLICATION BLOCKED — NOT PUBLISHED — NOT DEPLOYED. No image push or publication WIF exchange occurred because the entire publish job was skipped. The earlier six cloud prerequisite changes remain in place; no rollback was performed.
