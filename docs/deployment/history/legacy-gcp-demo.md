# Retired GCP Demo Architecture — Historical Record

Status: **RETIRED / NEVER INSTANTIATED**

This file preserves the audit meaning of the removed `infra/gcp-demo` source. It is historical
evidence, not an operator runbook. Do not reconstruct or execute the removed Terraform, Cloud Run,
Cloud SQL, runtime-GCS, IAM, WIF, or helper design from Git history.

The legacy design was introduced by `b4a8013c6e91cffcba8d099f6f816e55a4f31a28` and expanded with
guarded operator helpers by `fc1f7701478b349bf747f5abd09c7ab0e9427160`. Its pre-deployment gate
recorded local quality, Terraform validation with `-backend=false`, secret scanning, and image
builds. That gate explicitly stated that no Terraform apply or GCP resource creation occurred.

The deployment-evidence template remained pending for Terraform apply, Cloud SQL migration,
synthetic seed, LINE synchronization, and live smoke verification. Phase F5d correlated complete
repository/Git history, available operator history, organization-admin project enumeration,
per-project inventories, and full-project-lifetime Admin Activity. It proved:

- historical deployment project: none used;
- Cloud SQL: absent;
- Terraform backend/state: absent;
- runtime GCS bucket: absent; and
- live legacy deletion manifest: empty.

Phase F6 removed the callable/declarative repository source only. Current production remains GCE,
Compose, systemd, the external nginx TLS edge, the immutable GCE release workflow, and
`PLATFORM_TERRAFORM`. See
[`phase-f-legacy-inventory.md`](../phase-f-legacy-inventory.md) and
[`phase-f-removal-plan.md`](../phase-f-removal-plan.md) for the complete evidence and safety gates.
