resource "google_kms_key_ring" "pii" {
  project  = var.project_id
  name     = "strayhub-pii"
  location = var.region

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_kms_crypto_key" "pii" {
  name                       = "pii-encryption"
  key_ring                   = google_kms_key_ring.pii.id
  purpose                    = "ENCRYPT_DECRYPT"
  destroy_scheduled_duration = "2592000s"

  labels = {
    application = "strayhub"
    environment = "prod"
    phase       = "e2"
  }

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "SOFTWARE"
  }

  lifecycle {
    prevent_destroy = true
    # Imported operator labels appear as effective_labels. Preserve them without an adoption write.
    ignore_changes = [labels]
  }
}

resource "google_kms_crypto_key_iam_member" "runtime" {
  crypto_key_id = google_kms_crypto_key.pii.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = local.runtime_service_account
}
