output "web_service_url" {
  description = "Cloud Run URL for the Next.js Demo."
  value       = google_cloud_run_v2_service.web.uri
}

output "api_service_url" {
  description = "Cloud Run URL for the FastAPI Demo."
  value       = google_cloud_run_v2_service.api.uri
}

output "worker_service_name" {
  description = "Cloud Run Worker service name."
  value       = google_cloud_run_v2_service.worker.name
}

output "migration_job_name" {
  description = "Cloud Run Job used for controlled Alembic migration."
  value       = google_cloud_run_v2_job.migration.name
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL connection name for the migration/runtime boundary."
  value       = google_sql_database_instance.demo.connection_name
}

output "private_gcs_bucket" {
  description = "Private GCS bucket used by the Object Storage adapter."
  value       = google_storage_bucket.private.name
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository path for immutable images."
  value       = google_artifact_registry_repository.containers.name
}

output "webhook_https_url" {
  description = "HTTPS LINE Webhook reference; publish only after controlled deployment."
  value       = "${google_cloud_run_v2_service.api.uri}/v1/line/webhook"
  sensitive   = true
}

output "liff_https_url" {
  description = "HTTPS LIFF entry reference; publish only after controlled deployment."
  value       = "${google_cloud_run_v2_service.web.uri}/animal-confirmation"
  sensitive   = true
}

output "rich_menu_config" {
  description = "Versioned Rich Menu source; not a Terraform-managed resource."
  value       = "infra/gcp-demo/line-rich-menu.yaml"
}

output "runtime_service_account_emails" {
  description = "Runtime identities; keep deployment output access restricted."
  value = {
    for name, account in google_service_account.runtime : name => account.email
  }
  sensitive = true
}
