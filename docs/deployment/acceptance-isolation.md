# StrayHub Acceptance Isolation Contract

This contract governs the temporary `strayhub-acceptance` environment used by
Gate 3 and Gate 4. It is deliberately separate from production and fails closed
if any required boundary is absent.

## Fixed boundaries

- Compose project: `strayhub-acceptance`.
- Host bindings: `127.0.0.1:13000` for Web and `127.0.0.1:18080` for API.
- Public ingress: a dedicated, access-controlled HTTPS hostname proxies only to
  `127.0.0.1:13000` (`ACCEPTANCE_INGRESS_MODE=external-https-to-loopback-web`).
  It must not be `strayhub.enadv.quest`; port `18080` is diagnostics-only and
  must never be an ingress upstream.
- LINE: a dedicated acceptance Messaging API channel and LIFF app. Never change
  the production webhook. The acceptance channel webhook is
  `${WEB_PUBLIC_BASE_URL}/v1/line/webhook`.
- Data: `strayhub_acceptance` PostgreSQL database plus the three explicitly named
  acceptance volumes and `strayhub-acceptance-runtime` network.
- Queues: `acceptance-ai` and `acceptance-system`; worker concurrency is `1`.
- AI: `CELERY_AI_ENABLED=false`; service-account JSON keys are forbidden.
- Images: API, Worker, and Web must be exact `repository@sha256:digest` references
  from the current RC release bundle.

The HTTPS ingress/tunnel is host infrastructure, not part of Compose. It must be
allowlisted to the release team and terminated independently of production.

## Controlled LINE identities

`LINE_NOTIFICATION_RECIPIENT_ALLOWLIST_SHA256` contains comma-separated SHA-256
digests of at least two controlled acceptance LINE user IDs (for example, one
adopter and one staff identity). Store only the digests in the protected
non-secret acceptance config. The central Messaging API adapter blocks every
acceptance push whose recipient digest is absent; it does not log the recipient.

Generate a digest without printing the source identity:

```bash
read -rs LINE_TEST_USER_ID
printf %s "$LINE_TEST_USER_ID" | shasum -a 256
unset LINE_TEST_USER_ID
```

## Secret materialization

Create dedicated `strayhub-acceptance-*` Secret Manager values. Database URLs
must use `postgres:5432/strayhub_acceptance`, the runtime role must be
`strayhub_acceptance_app`, and the broker must use authenticated `redis:6379`.
Then materialize them atomically:

```bash
sudo ./infra/gce/scripts/fetch-secrets.sh \
  --project canvas-primacy-502703-k1 \
  --environment acceptance \
  --output-root /var/lib/strayhub/acceptance/secrets \
  --secret-map ./infra/gce/secrets/acceptance-secret-map.tsv
```

This read-only operation does not use or create a service-account JSON key.

## Gate 3 static preflight

Copy `.env.acceptance.template` to a protected host path, fill the non-secret
values, and set mode `0600`. Before Gate 3 passes, run only:

```bash
./infra/gce/scripts/acceptance-preflight.sh \
  --config-env /etc/strayhub/acceptance.env \
  --image-env /path/to/current-rc/image-digests.env \
  --secrets-root /var/lib/strayhub/acceptance/secrets
```

The preflight renders and validates the complete Compose model. It intentionally
does not pull images, create resources, run migrations, or start containers.
Gate 4 runtime commands are prohibited until this reports PASS and the release
approver records Gate 3 approval.

## Cleanup boundary

After Gate 4, the only authorized destructive command is the scoped cleanup:

```bash
./infra/gce/scripts/cleanup-acceptance.sh \
  --config-env /etc/strayhub/acceptance.env \
  --runtime-env /var/lib/strayhub/acceptance/secrets/current/runtime.env \
  --image-env /path/to/current-rc/image-digests.env \
  --confirm CLEAN_STRAYHUB_ACCEPTANCE
```

It invokes Compose only for project `strayhub-acceptance`, removes that project's
containers/network/volumes, and verifies no labeled resources remain. It never
uses `docker system prune`, `docker volume prune`, or removes production files.
Secret generations remain for audit and require a separate approved retention
procedure.
