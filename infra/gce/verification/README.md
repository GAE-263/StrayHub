# RUNTIME-GENERATED VERIFICATION MATERIAL

Phase B1 JWT keys are generated locally after checkout. No private or public PEM fixture is committed
to Git.

`infra/gce/scripts/preflight.sh` invokes `generate-verification-jwt-keys.sh`. The generator creates an
RSA 2048-bit PKCS#8 private key and its derived public key under the ignored `generated/` directory.
It reuses an existing valid matching pair, repairs its permissions, and replaces it only when either
file is missing or invalid. Operators may explicitly rotate the local pair with:

```bash
./infra/gce/scripts/generate-verification-jwt-keys.sh --force
```

Generated files:

- `generated/jwt-private.pem` — mode `0600`
- `generated/jwt-public.pem` — mode `0644`

The generated pair is synthetic local/CI verification material. It MUST NOT be used in any real GCE,
production, staging, shared demo, or externally reachable deployment. It MUST NOT be uploaded to
Secret Manager. Real deployments must inject JWT private/public keys from Secret Manager or another
explicitly approved production secret source through protected, non-repository paths.

Deleting `generated/` is safe; the next preflight creates a fresh pair. Git ignores the directory,
Docker excludes it from all build contexts, and Compose mounts its files read-only into API only.
Neither the generator nor preflight prints private key contents.

Tests use `STRAYHUB_VERIFICATION_JWT_DIR` to direct the generator into an isolated temporary
directory. This override is for verification tooling only and is not an approved deployment key
source.
