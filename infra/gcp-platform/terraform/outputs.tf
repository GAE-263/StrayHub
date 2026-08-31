output "retained_resource_ids" {
  description = "Non-secret identities owned by PLATFORM_TERRAFORM."
  value = {
    secrets       = sort([for secret in google_secret_manager_secret.production : secret.id])
    kms_key       = google_kms_crypto_key.pii.id
    backup_bucket = google_storage_bucket.backups.id
    state_bucket  = google_storage_bucket.platform_state.id
  }
}
