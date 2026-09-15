# Local Docker Staging (manual, no new GCP VM)

Use an already published, trusted StrayHub release artifact digest. The runner downloads its
bundle, validates checksums and release identity, extracts it safely, and uses its production
Compose definition with the repository's local staging override. It never rebuilds images.
Registry authentication and any registry storage/download charges still apply.

## Preparation

1. Run Docker locally with Compose supporting `!override` / `!reset` and amd64 emulation on
   Apple Silicon. Use `docker context ls` to choose an explicitly local Unix-socket context
   (usually `desktop-linux` on Docker Desktop). Do not select a forwarded remote socket.
2. Copy `infra/local/staging.env.template` to a protected directory **outside the repository**;
   set permissions to `0600`. Replace every `REPLACE` value with dedicated local values.
   Generate passwords with `openssl rand -hex 24` and the AES key with `openssl rand -base64 32`.
   The two database URLs must match their corresponding database passwords. Do not copy
   production secrets, database backups, LINE credentials or cloud service-account files.
3. Generate a dedicated RSA key pair in that protected directory:

   ```bash
   openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out staging-jwt-private.pem
   chmod 600 staging-jwt-private.pem
   openssl pkey -in staging-jwt-private.pem -pubout -out staging-jwt-public.pem
   ```

   Put the absolute key paths in the env file. Keep these keys stable while retaining data.
4. Authenticate Docker to the release registry using your existing authorized identity.
   Obtain the artifact `repository@sha256:...` from a successful trusted publisher run.
   A tag, unmerged source tree, or synthetic test manifest is not a release artifact.

## Run from the repository root

```bash
uv run python -m scripts.local_staging \
  --context desktop-linux \
  --artifact 'REGISTRY/strayhub-release@sha256:EXACT_64_HEX_DIGEST' \
  --env-file /absolute/protected/staging.env \
  --work-dir /absolute/protected/staging-attempt-001 \
  --confirm-local-secrets
```

The attempt directory must not exist; each attempt gets its own evidence. Application
containers of project `strayhub-staging` are stopped before migration. Its persistent database,
storage and Redis volumes are retained. Never run concurrent staging attempts on this project.
Changing database initialization passwords does not rotate an existing database volume.

API: `http://127.0.0.1:18082`; Web: `http://127.0.0.1:13002`. A secret-free, read-only edge
container is the only service connected to the ingress network and both ports bind to loopback.
API and Web remain exclusively on the internal runtime network. Postgres, MinIO and Redis have no
published ports. The internal Docker network blocks outbound
LINE/AI/cloud calls; LINE login, LIFF and cloud KMS are intentionally not validated. `APP_ENV=local`
uses the application's local configuration policy, not its production fail-fast policy.

After migration, the runner reads back the exact Alembic revision, bootstraps deterministic
synthetic tenants through the explicitly guarded operator path, and executes authenticated API,
QR/care-report and cross-shelter denial checks using the non-superuser runtime database role. It
also probes both loopback endpoints. Only then does `staging-receipt.json` bind the results to the
git SHA, artifact/image digests, bundle/manifest hashes and staging contract hashes. Worker/Beat
checks establish running state, **not successful task execution**. Failures do not generate a
receipt. Containers and volumes are left available for diagnosis;
captured tool output is suppressed because it can include credentials.

Inspect only this project using Docker Desktop or focused container logs. To stop it without
deleting data, select the `strayhub-staging` project in Docker Desktop and stop it. This runner
does not delete volumes, manage production, create cloud resources or modify CI promotion gates.

## Acceptance boundaries

This completes the local Docker portion of Phase 4, but does not authorize production promotion.
The bootstrap still requires both the dedicated environment flag and CLI confirmation, accepts
only synthetic fixture identities, and is now explicitly valid in `APP_ENV=local`. GCP
WIF/IAP/IAM, KMS and public HTTPS/systemd checks remain separate production/cloud acceptance
requirements. The receipt records cloud checks as not applicable locally, is not a signed CI
attestation, and always says `production_promotion_approved: false`.
