# PLATFORM_TERRAFORM

This root owns only retained/shared StrayHub production platform resources. It does not own the
GCE host, public edge, DNS/TLS, legacy Cloud Run/Cloud SQL/runtime GCS, secret values, secret
versions, application releases, or unrelated project resources.

The GCS backend is the dedicated private, uniform-access, public-access-prevented, versioned bucket
`strayhub-platform-tfstate-canvas-primacy-502703-k1`, prefix `strayhub/platform`. Do not point this
root at the legacy `strayhub/gcp-demo` prefix or the runtime backup bucket.

Managed retained resources:

- eleven `strayhub-prod-*` Secret Manager resource metadata objects and the exact
  `strayhub-gce-sa` accessor member on each;
- `asia-east1/keyRings/strayhub-pii/cryptoKeys/pii-encryption` and its exact runtime member; and
- the production backup bucket, retention/lifecycle/soft-delete configuration, exact runtime
  creator/viewer members, and the platform state bucket itself.

Every critical resource has `prevent_destroy`. Secret payloads and versions are deliberately absent
from this root and state.

## Safe operator sequence

Authenticate with an approved short-lived operator identity, then initialize and validate:

```bash
terraform -chdir=infra/gcp-platform/terraform init -input=false
terraform -chdir=infra/gcp-platform/terraform validate
```

Existing resources are adopted one exact address at a time. The reviewed F5b import ledger is in
`docs/deployment/platform-terraform.md`. Never improvise an address or import a secret version.

After adoption, require:

```bash
terraform -chdir=infra/gcp-platform/terraform plan \
  -input=false \
  -lock=false \
  -var=project_id=canvas-primacy-502703-k1
```

The accepted result is `No changes`. Do not apply a change merely to make the live retained
resource match this code. Update and review the declaration when it does not accurately describe
the existing resource.

`terraform destroy`, `terraform state rm`, and `terraform state mv` are prohibited for this root.
