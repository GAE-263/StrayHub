locals {
  production_secret_ids = toset([
    "strayhub-prod-animal-confirmation-secret",
    "strayhub-prod-celery-broker-url",
    "strayhub-prod-database-migration-url",
    "strayhub-prod-database-url",
    "strayhub-prod-jwt-private-key",
    "strayhub-prod-jwt-public-key",
    "strayhub-prod-line-channel-access-token",
    "strayhub-prod-line-channel-secret",
    "strayhub-prod-login-abuse-hmac-secret",
    "strayhub-prod-gemini-api-key",
    "strayhub-prod-minio-access-key",
    "strayhub-prod-minio-secret-key",
    "strayhub-prod-postgres-password",
    "strayhub-prod-postgres-runtime-password",
    "strayhub-prod-redis-password",
    "strayhub-prod-stool-api-key",
  ])

  runtime_service_account = "serviceAccount:strayhub-gce-sa@${var.project_id}.iam.gserviceaccount.com"
  backup_bucket_name      = "strayhub-backups-${var.project_id}"
  state_bucket_name       = "strayhub-platform-tfstate-${var.project_id}"
}
