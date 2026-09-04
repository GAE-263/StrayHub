# Remote Management Demo Decision

Status: **NOT IMPLEMENTED — local-only management**
Decision date: 2026-09-04
Owner basis: no explicit product-owner requirement authorizes public management exposure.

The LINE/LIFF tunnel is not a management-demo tunnel. It rejects `/login`, management pages,
`/v1/management/**`, platform governance, organization administration, docs/debug endpoints, and
unregistered routes before they reach Next.js or FastAPI.

If a remote management demonstration becomes a real requirement, define it as a separate
deployment/profile feature with an explicit owner, verified synthetic-only database, ephemeral
credential and session expiry, visible exposure warning, and stop-time revocation. Do not extend
the LINE allowlist or reuse `demo-line.sh` as a shortcut.
