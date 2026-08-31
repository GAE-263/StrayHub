# Cloud KMS PII Encryption Contract

Status: Phase E2 live VM ADC encrypt/decrypt and key-scoped IAM accepted

## Provider boundary

StrayHub uses the existing `PiiCipher` port for volunteer application PII. Provider selection is
environment-bound:

| Runtime | Provider | Purpose |
| --- | --- | --- |
| `local`, `test`, `testing` | existing `local-aes-gcm`, only when explicitly allowed | developer and automated tests |
| every non-local environment | `gcp-kms` | canonical PII encryption provider |

Non-local configuration cannot select or fall back to the local provider. The API dependency builds
the existing `GoogleCloudKmsPiiCipher` from `Settings`; Worker, Migration, Web, nginx, PostgreSQL,
and MinIO do not construct this PII cipher. D2 does not change volunteer behavior, tenant checks,
the PII domain model, database columns, or encrypted-data semantics.

## CryptoKey resource

`PII_KMS_KEY_NAME` is a non-secret, environment-specific full CryptoKey resource name:

```text
projects/<project>/locations/<location>/keyRings/<ring>/cryptoKeys/<key>
```

The production template intentionally leaves it empty. Settings, the adapter, and production
preflight reject missing or structurally invalid values. No project, key ring, key, key material, or
service-account credential is generated or hard-coded by D2.

Encrypt requests use the configured CryptoKey name, UTF-8 plaintext bytes, and the existing
field-scoped additional authenticated data: organization ID, application ID, field name, and schema
version. Cloud KMS encrypts with the CryptoKey's primary version. The adapter stores the returned
full CryptoKeyVersion name alongside the ciphertext and provider algorithm.

Decrypt requests remain bound to the configured CryptoKey and the same authenticated context. Cloud
KMS selects the ciphertext's version, so data encrypted by an older version remains decryptable only
while that version remains enabled. A stored version from another CryptoKey is rejected before a
decrypt call. D2 does not create rotation, re-encryption, disablement, or destruction policy.

## Authentication and IAM

Canonical production authentication is:

```text
GCE VM service account
  -> Application Default Credentials from the metadata service
  -> google-cloud-kms client
  -> configured CryptoKey
```

Downloaded service-account JSON keys are not part of the production design and must not be placed in
Git, Secret Manager staging, Compose env files, images, or host configuration. Local automated tests
inject a mock client through the existing adapter seam and never acquire ADC.

The GCE VM service account is the principal. Grant
`roles/cloudkms.cryptoKeyEncrypterDecrypter` on the specific PII CryptoKey where practical. Do not
grant project Editor/Owner, Cloud KMS Admin, or project-wide crypto access. D2 performs no IAM
mutation. Because the planned identity is VM-scoped, Phase E must verify metadata-service exposure
and container isolation; Compose passes KMS configuration only to API, but environment scoping alone
does not create a distinct container identity.

## Failure and leakage behavior

The adapter fails closed when configuration, client creation, KMS access, permissions, network
transport, response shape, key-version metadata, authenticated context, ciphertext, or plaintext
decoding is invalid. It returns the existing safe `503` domain errors and never switches to local
AES in a non-local runtime.

Application and verification output must not contain plaintext, raw ciphertext, credentials, or key
material. Database persistence continues to contain only ciphertext, algorithm, and returned key
version metadata. Audit records remain metadata-only, and reveal still requires the existing audit
and tenant authorization path before decryption.

## Preflight and local verification

Production config keeps:

```text
PII_ENCRYPTION_PROVIDER=gcp-kms
PII_KMS_KEY_NAME=<full CryptoKey resource name>
```

`production-preflight.sh` verifies both values and the non-local settings policy. It deliberately
does not call KMS, fetch credentials, or generate keys, keeping startup validation deterministic.
The `google-cloud-kms` client uses ADC only when the API first resolves the production PII cipher.

Focused local tests inject a synthetic client and prove the exact resource name and authenticated
request shape, non-empty ciphertext, round-trip equality, returned version preservation, old-version
decrypt behavior, permission-denied failure, malformed-ciphertext failure, and no local fallback.
Only synthetic applicant values and random tenant/application identifiers are used.

## Phase E2 live acceptance

The dedicated live resource is
`projects/canvas-primacy-502703-k1/locations/asia-east1/keyRings/strayhub-pii/cryptoKeys/pii-encryption`.
The keyless VM service account has `roles/cloudkms.cryptoKeyEncrypterDecrypter` only on that
CryptoKey. It has no KMS Admin, Editor, Owner, or project-wide crypto binding.

`verify-live-kms.py` selects the existing non-local `gcp-kms` adapter, obtains ADC from VM metadata,
and uses synthetic plaintext plus field-scoped authenticated data. Live encrypt, decrypt, exact
round-trip equality, returned key-version scope, and malformed-ciphertext fail-closed behavior passed.
The verifier prints neither plaintext nor ciphertext and cannot enable the local AES provider.

The ring, key, and binding were created with controlled `gcloud` commands because canonical
managed-service IaC ownership is not settled. A later remote-state/ownership review must adopt or
replace this procedure without modifying legacy state in place.

## Deferred boundaries

- Phase E3: application deployment and operational supervision.
- Phase F: legacy Cloud Run/Cloud SQL/Terraform cleanup and deployment CI replacement.

No legacy infrastructure, Terraform state, DNS, firewall, TLS, systemd, schema, product behavior, or
LINE/LIFF integration changes are authorized by D2.
