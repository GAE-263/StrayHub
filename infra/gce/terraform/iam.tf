resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = var.service_account_id
  display_name = "StrayHub canonical GCE runtime"
  description  = "Metadata-server identity for the canonical single-VM deployment"
}

# E1 creates identity only. Secret/KMS/GCS grants require exact resource-level review in E2.
