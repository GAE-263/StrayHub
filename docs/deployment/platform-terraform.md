# PLATFORM_TERRAFORM Operations and F5b Adoption Ledger

Status: **ADOPTED — NO CHANGES**

Adoption date: 2026-08-31

This root owns retained/shared production platform resources only. It does not own GCE, the public
edge, DNS/TLS, application releases, legacy Cloud Run/Cloud SQL/runtime GCS, or unrelated project
resources. Secret payloads and versions are absent from source and state.

## Backend boundary

| Field | Value |
| --- | --- |
| Bucket | `strayhub-platform-tfstate-canvas-primacy-502703-k1` |
| Prefix | `strayhub/platform` |
| Location | `asia-east1` |
| Uniform access | enabled |
| Public access prevention | enforced |
| Object versioning | enabled |
| Soft delete | 604800 seconds |
| Runtime VM access | none granted |

The state bucket is separate from both the production backup bucket and the unknown legacy backend.
It was created as the F5b ownership-support resource before backend initialization, then imported
into its own root with `prevent_destroy`. It contains Terraform state metadata, not secret values.

## Imported addresses

The following 29 addresses were imported one at a time with the exact live identity:

```text
google_storage_bucket.platform_state
google_storage_bucket.backups
google_kms_key_ring.pii
google_kms_crypto_key.pii
google_kms_crypto_key_iam_member.runtime
google_storage_bucket_iam_member.runtime_creator
google_storage_bucket_iam_member.runtime_viewer

google_secret_manager_secret.production["strayhub-prod-animal-confirmation-secret"]
google_secret_manager_secret.production["strayhub-prod-database-migration-url"]
google_secret_manager_secret.production["strayhub-prod-database-url"]
google_secret_manager_secret.production["strayhub-prod-jwt-private-key"]
google_secret_manager_secret.production["strayhub-prod-jwt-public-key"]
google_secret_manager_secret.production["strayhub-prod-line-channel-access-token"]
google_secret_manager_secret.production["strayhub-prod-line-channel-secret"]
google_secret_manager_secret.production["strayhub-prod-minio-access-key"]
google_secret_manager_secret.production["strayhub-prod-minio-secret-key"]
google_secret_manager_secret.production["strayhub-prod-postgres-password"]
google_secret_manager_secret.production["strayhub-prod-postgres-runtime-password"]

google_secret_manager_secret_iam_member.runtime["strayhub-prod-animal-confirmation-secret"]
google_secret_manager_secret_iam_member.runtime["strayhub-prod-database-migration-url"]
google_secret_manager_secret_iam_member.runtime["strayhub-prod-database-url"]
google_secret_manager_secret_iam_member.runtime["strayhub-prod-jwt-private-key"]
google_secret_manager_secret_iam_member.runtime["strayhub-prod-jwt-public-key"]
google_secret_manager_secret_iam_member.runtime["strayhub-prod-line-channel-access-token"]
google_secret_manager_secret_iam_member.runtime["strayhub-prod-line-channel-secret"]
google_secret_manager_secret_iam_member.runtime["strayhub-prod-minio-access-key"]
google_secret_manager_secret_iam_member.runtime["strayhub-prod-minio-secret-key"]
google_secret_manager_secret_iam_member.runtime["strayhub-prod-postgres-password"]
google_secret_manager_secret_iam_member.runtime["strayhub-prod-postgres-runtime-password"]
```

No import address refers to a secret version. IAM resources are non-authoritative member resources
for only `strayhub-gce-sa`; they do not replace whole policies.

## Adoption plan evidence

The first post-import plan proposed 13 label-only in-place changes and no additions or deletions.
F5b stopped without applying. The provider reports operator-created labels as `effective_labels`,
not Terraform-configured `labels`; the declarations keep expected create-time labels but explicitly
ignore label adoption so the live metadata is preserved without a write.

After that declaration correction:

```text
Plan: No changes.
Exit: 0
```

No `terraform apply`, `destroy`, `state rm`, or `state mv` was run. Imports changed only the new
remote Terraform state. Live secret metadata/IAM, KMS, backup configuration/IAM and backup objects
were not changed.

## Required plan command

Use a short-lived approved operator credential:

```bash
terraform -chdir=infra/gcp-platform/terraform init -input=false
terraform -chdir=infra/gcp-platform/terraform plan \
  -input=false \
  -lock=false \
  -var=project_id=canvas-primacy-502703-k1
```

Only `No changes` is acceptable during F5b/F6 readiness. A proposed retained-resource modification
must be reviewed as a new infrastructure change; never apply merely to silence drift.

## Safety rules

- Never add `google_secret_manager_secret_version` or payload data to this root.
- Never point this root at `strayhub/gcp-demo` or the backup bucket.
- Never grant the GCE runtime identity access to the Terraform state bucket.
- Never use whole-policy IAM resources where an exact member resource is sufficient.
- Never remove `prevent_destroy` as part of legacy cleanup.
- Never use this root to manage legacy or unrelated resources.
