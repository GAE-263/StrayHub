resource "google_artifact_registry_repository" "containers" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repository_id
  description   = "StrayHub GCP Demo container images"
  format        = "DOCKER"
  labels        = local.labels

  depends_on = [google_project_service.required]
}

resource "google_logging_project_bucket_config" "demo" {
  project          = var.project_id
  location         = "global"
  bucket_id        = "${var.name_prefix}-logs"
  retention_days   = 30
  enable_analytics = false
  description      = "Short-lived Demo logs; application masking remains mandatory."

  depends_on = [google_project_service.required]
}

resource "google_logging_metric" "cloud_run_errors" {
  project = var.project_id
  name    = "${var.name_prefix}-cloud-run-errors"
  filter  = "resource.type=\"cloud_run_revision\" AND severity>=ERROR"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}
