# Canonical GCE host Terraform

This isolated subtree owns the GCE host foundation: custom VPC/subnet, minimal ingress,
regional static IPv4, dedicated metadata-server service account, and one GCE VM. It never owns or
imports legacy `infra/gcp-demo` resources, managed-service IAM, secrets, KMS keys, backup buckets,
DNS, certificates, or application deployment.

E1 was applied and accepted through the reviewed saved-plan workflow. E4 replaces the GCE public
80/443 rule with Web/API upstream ingress restricted to the existing edge `34.10.249.63/32`; IAP
SSH remains unchanged. OS Login profile keys are operator-owned outside Terraform. Local state remains in use
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

Never apply an unsaved or unreviewed plan.
