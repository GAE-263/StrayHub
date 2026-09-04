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

No Phase B–E implementation was performed. In particular, this phase does not add a management
registry compiler, shared-demo nginx routes, public Host policy, remote session origin, rollback
automation, or public remote-login smoke testing.
