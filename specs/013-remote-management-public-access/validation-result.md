# Validation Result: Remote Management Public Access

## Phase A — Auth Protection

**Date**: 2026-09-05
**Status**: PASS — T001–T013 complete
**Activation status**: Not activated. `/login` and management routes remain outside the shared
public tunnel.

### Verified behavior

- Account abuse keys use a dedicated HMAC-SHA256 secret and NFKC → trim → casefold normalization;
  authentication lookup still receives the original submitted username.
- PostgreSQL stores only account/IP digests. It atomically serializes absent and existing rows with
  transaction advisory locks.
- Account failures 1–4 return the generic 401 contract. Failure 5 creates a 15-minute lock and
  returns the generic 429 contract with `Retry-After`; a correct password cannot bypass an active
  lock. Expiry at the 15-minute boundary resets the state.
- The source-IP rolling window admits 20 attempts, rejects attempt 21 without inserting another
  event, and recovers after the oldest event expires. Successful login clears only account state.
- Concurrent account/IP tests use real PostgreSQL transactions and deterministic events rather than
  sleeps. A separate SQLAlchemy engine sees persisted lock state, representing worker/process pool
  replacement.
- Direct mode uses the socket peer and ignores forwarding headers. Trusted-proxy mode accepts one
  canonical IPv4/IPv6 value only from the configured loopback gateway metadata header; missing,
  forged, duplicate, or invalid metadata fails closed.
- Unknown and unusable accounts execute one Argon2 verification against a valid fixed dummy hash and
  retain the same outward wrong-credential behavior. This narrows obvious timing differences; it is
  not claimed to be perfectly constant-time.
- Synthetic raw account, password, and IP sentinels were absent from captured application logs. The
  existing centralized logging and audit-redaction regression tests remain green.

### Evidence

- Phase A schema/unit/security/integration/auth targeted matrix: PASS.
- Broader authentication contract, adapter, session, scope, and role regressions: PASS.
- Existing sensitive logging, audit, static-policy, and URL-registry regressions: PASS.
- Acceptance bootstrap and local authentication compatibility: PASS.
- Alembic: one head (`0045_remote_login_abuse`); actual `0045 → 0044 → head` cycle: PASS.
- Ruff lint/format for touched files: PASS.
- Mypy project boundary and all eight touched production modules: PASS.
- `git diff --check`: recorded in final Phase A handoff.

### Scope boundary

At the Phase A checkpoint, no Phase B–E implementation was performed. In particular, Phase A did
not add a management
registry compiler, shared-demo nginx routes, public Host policy, remote session origin, rollback
automation, or public remote-login smoke testing.

## Phase B — Shared Profile Contracts

**Date**: 2026-09-05
**Status**: PASS — T014–T022 implemented and locally validated
**Activation status**: Not activated. Runtime routing, nginx, tunnel launchers, and public exposure
remain unchanged; those begin in Phase C.

### Contract result

- Management registry: 23 effective routes, all carrying explicit FR-004 metadata plus
  `category` and `demo_required`. Platform administration, volunteer PII surfaces, broad API/UI
  patterns, unanchored patterns, malformed paths, unsupported methods/upstreams, and unknown
  security policy values fail closed.
- LINE registry: 25 existing routes are consumed read-only through compatibility metadata. The
  source digest is pinned by a deterministic contract test; the 013 compiler does not copy or
  rewrite LINE route definitions.
- Profiles: `line-only` compiles to 25 routes; `shared-demo-dev` compiles to 48 routes and retains
  the existing bounded Next static/HMR entries; `shared-demo-production` compiles to 46 routes,
  excludes both development entries, and adds exact manifest-proven assets.
- Composition: unknown profiles, registries, exclusions, duplicate IDs, incomplete LINE metadata,
  and overlapping method/path contracts with different upstream or security policy fail closed.
- Host policy: shared profiles require a runtime-only origin. Public origins require exact HTTPS
  authority and reject userinfo, wildcard, path, query, fragment, non-default port, malformed
  authority, and loopback. Loopback HTTP is accepted only with the explicit local-test flag. Host
  comparison is IDNA/case/port normalized and exact.
- Next assets: Next 15 `build-manifest.json` and `app-build-manifest.json` are parsed for the
  allowlisted pages, applicable layouts, shared runtime chunks, JS, and CSS. Source maps,
  `/_next/image`, non-static paths, unlisted pages, unknown internals, and unresolved manifests
  fail closed. No chunk filename is committed as policy.
- RSC: no blanket `_rsc` route exists. The allowlisted page path and its ordinary preserved query
  contract remain the boundary.

### Verification evidence

- Phase B contract/unit matrix: 56 passed; settings regression matrix: 27 passed.
- Real `npm --prefix apps/web run build`: PASS (Next.js 15.5.24, 25 static pages generated).
- Production compiler against the fresh real `.next` manifests: PASS; 29 exact JS/CSS assets
  resolved for the 12 registry route IDs / 13 concrete pages.
- Ruff lint and format for touched Python files: PASS.
- Mypy for the compiler and settings boundary: PASS.
- No actual ngrok hostname is stored; tests use reserved documentation domains only.

### Known boundary and compatibility notes

- The authoritative 012 LINE registry is committed upstream in `9015166`; 013 reads and composes
  that source contract without taking ownership or creating a duplicate allowlist.
- Existing LINE UUID patterns such as `[0-9a-fA-F-]{36}` are preserved as legacy 012 semantics.
  Management patterns require canonical UUID bounds. Tightening LINE patterns is outside Phase B.
- No current registry/profile discrepancy prevented compilation. Runtime deny/allow behavior is
  not claimed here because nginx generation and integration tests belong to Phase C.
