# Guarded Acceptance Bootstrap

Status: Phase E5b operator capability
Migration: **NONE**

`scripts/bootstrap_acceptance.py` creates the minimum deterministic, synthetic fixtures needed to
exercise StrayHub's deployed password authentication, tenant isolation, volunteer authorization,
QR-first animal selection, and care-report flow. It is a server-side operator command, not an HTTP
endpoint or alternate authentication mechanism. The resulting users authenticate through the
normal `/login` route, production password hashing, session creation, and JWT verification.

## Safety boundary

All of the following are required before the command imports the runtime database engine:

- `APP_ENV` is exactly `acceptance`, `demo`, or `gcp-demo`;
- `STRAYHUB_ALLOW_ACCEPTANCE_BOOTSTRAP=true` is present;
- the operator supplies `--confirm-synthetic-data`; and
- exactly one protected password source is supplied.

The preferred password source is a root/operator-managed regular file:

```bash
APP_ENV=acceptance \
STRAYHUB_ALLOW_ACCEPTANCE_BOOTSTRAP=true \
ACCEPTANCE_BOOTSTRAP_PASSWORD_FILE=/run/secrets/acceptance-bootstrap-password \
uv run python -m scripts.bootstrap_acceptance --confirm-synthetic-data
```

On the canonical Compose host, layer `infra/gce/docker-compose.acceptance.yml` after the production
base definition. Despite that base filename, the rendered project is the fully isolated
`strayhub-acceptance` topology: dedicated PostgreSQL, Redis, MinIO, network, volumes, ports, LINE
channel, secrets, and immutable RC images. It never reuses a production data service. Run the
bootstrap only after Gate 3 passes and the acceptance PostgreSQL service is healthy. Use
`infra/gce/scripts/run-acceptance-bootstrap.sh` as the one-shot entrypoint; it loads acceptance JWT
files into that process and executes the guarded CLI.

The bootstrap uses the migration role because organization creation spans RLS-protected tenant and
policy tables. This is an operator data-provisioning boundary, not a runtime privilege change. The
later acceptance login uses the running API's normal password verification and JWT issuance.

The password file must have no group or other permission bits (normally mode `0600`) and contain a
password of at least 20 characters. `ACCEPTANCE_BOOTSTRAP_PASSWORD` is supported for controlled
automation, but its value must never be placed in shell history, process diagnostics, source,
documentation, or logs. Set exactly one of the file and environment-variable sources.

Use `--dry-run` with the same guards to validate database reachability and planned actions. The
command runs the complete canonical service/repository flow in a transaction and then rolls it
back. The normal form commits once after every fixture succeeds; failures roll back the entire
transaction.

The canonical host invocation uses the production base Compose followed by the acceptance override,
the dedicated acceptance config, secrets and current RC image digests, the explicit allow flag, the
protected acceptance password mount, and the wrapper entrypoint. In abbreviated operator form:

```bash
docker compose \
  --project-name strayhub-acceptance \
  --file infra/gce/docker-compose.production.yml \
  --file infra/gce/docker-compose.acceptance.yml \
  --env-file /etc/strayhub/acceptance.env \
  --env-file /var/lib/strayhub/acceptance/secrets/current/runtime.env \
  --env-file /path/to/current-rc/image-digests.env \
  run --rm --no-deps \
  -e STRAYHUB_ALLOW_ACCEPTANCE_BOOTSTRAP=true \
  -e ACCEPTANCE_BOOTSTRAP_PASSWORD_FILE=/run/secrets/acceptance-bootstrap-password \
  -v /var/lib/strayhub/acceptance/secrets/current/acceptance-bootstrap-password:/run/secrets/acceptance-bootstrap-password:ro \
  --entrypoint /app/infra/gce/scripts/run-acceptance-bootstrap.sh \
  api --confirm-synthetic-data
```

The deployment wrapper must also mount the tracked CLI/wrapper files read-only from the active
release and the root-owned password file read-only at the path shown above. Add `--dry-run` after the
confirmation flag for the rollback-only check. Never substitute a password value on this command
line.

## Deterministic fixtures

The command creates or reuses only unmistakably synthetic data:

| Fixture | Synthetic key | Scope |
| --- | --- | --- |
| Tenant A | `STRAYHUB-ACCEPTANCE-A` | Positive acceptance tenant |
| Admin A | `acceptance-admin-a@strayhub.local` | Tenant A only |
| Volunteer A | `acceptance-volunteer-a@strayhub.local` | Tenant A only |
| Volunteer membership/grant | Service-created active grant | Tenant A only, seven-day window |
| Animal A | `ACCEPTANCE-A-ANIMAL` | Tenant A only |
| QR/reportable scope A | Canonical service-generated records | Volunteer A and Animal A |
| Tenant B | `STRAYHUB-ACCEPTANCE-B` | Negative isolation tenant |
| Admin B | `acceptance-admin-b@strayhub.local` | Tenant B only |
| Animal B | `ACCEPTANCE-B-ANIMAL` | Tenant B only |

The CLI prints safe UUIDs and `created`, `reused`, or `updated` status. It never prints the
password, password hash, JWT, JWT signing material, or raw QR token. It uses application services,
repositories, tenant context, domain validation, Argon2 password hashing, and normal audit records;
fixture creation uses no raw SQL.

## Idempotency and ownership

Run the exact command twice after an approved deployment. The first successful run may report
`created`; the second must report `reused` unless an explicitly repairable fixture or expiring grant
needed an `updated` status. A collision with non-synthetic or malformed state fails closed instead
of hiding the conflict. The command does not duplicate users, memberships, grants, animals, QR
records, or reportable scopes.

The protected password file is operational secret material owned by the deployment operator. It is
not committed and must remain outside the release tree with mode `0600`. Rotate it by replacing the
protected runtime value and rerunning the bootstrap; the canonical production hash is updated.

Keep the synthetic fixtures after acceptance so tests are repeatable and audit history remains
truthful. Do not delete rows directly. Any future cleanup must use a separately reviewed,
domain-supported operation. Never put real PII into these fixtures.

## Prohibited uses

This command must not become a general demo-auth feature. Do not add a debug login endpoint, magic
header, forged-token path, client-side signing, JWT-private-key export, RLS exception, global
volunteer grant, or production customer data. Real-device LINE/LIFF testing continues to use the
normal LINE-verified flow and is outside this bootstrap.
