# Canonical GCE host Terraform

This isolated subtree owns the GCE host foundation: custom VPC/subnets, minimal ingress,
regional static IPv4 addresses, dedicated metadata-server service account, and the GCE VMs. It never owns or
imports retired legacy GCP-demo resources, managed-service IAM, secrets, KMS keys, backup buckets,
DNS, certificates, or application deployment.

The canonical target is now `us-central1` / `us-central1-c`, colocated with the retained nginx edge.
After the migration, Terraform deliberately retains the stopped `asia-east1-b` VM, its subnet, and
`34.81.77.204` address with `prevent_destroy`. It creates a stopped-disk snapshot in `us-central1`,
then creates the new VM from that snapshot. Do not remove the rollback resources until extended public routing,
PostgreSQL, MinIO animal photos, LINE webhook behavior, backups, and rollback have all been accepted.

E1 was applied and accepted through the reviewed saved-plan workflow. The application Web/API
upstreams now accept only nginx private IP `10.128.0.5/32` across bidirectional VPC peering; IAP SSH
remains unchanged. OS Login profile keys are operator-owned outside Terraform. Local state remains in use
because no remote backend is approved. Before any future infrastructure change, select a dedicated
remote-state backend, review state migration separately, enable only approved APIs, and repeat the
applicable identity and plan gates in `docs/deployment/gce-provisioning.md`.

```bash
terraform init
terraform fmt -recursive -check
terraform validate
terraform plan \
  -var='project_id=canvas-primacy-502703-k1' \
  -out=terraform.tfplan
terraform show terraform.tfplan
```

Never apply an unsaved or unreviewed plan. The first migration plan must report exactly
`4 to add, 0 to change, 0 to destroy`.
