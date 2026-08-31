resource "google_storage_bucket" "backups" {
  project                     = var.project_id
  name                        = local.backup_bucket_name
  location                    = var.region
  storage_class               = "STANDARD"
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  retention_policy {
    retention_period = 604800
    is_locked        = false
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 35
    }
  }

  soft_delete_policy {
    retention_duration_seconds = 604800
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_storage_bucket_iam_member" "runtime_creator" {
  bucket = google_storage_bucket.backups.name
  role   = "roles/storage.objectCreator"
  member = local.runtime_service_account
}

resource "google_storage_bucket_iam_member" "runtime_viewer" {
  bucket = google_storage_bucket.backups.name
  role   = "roles/storage.objectViewer"
  member = local.runtime_service_account
}

resource "google_storage_bucket" "platform_state" {
  project                     = var.project_id
  name                        = local.state_bucket_name
  location                    = var.region
  storage_class               = "STANDARD"
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  labels = {
    application = "strayhub"
    environment = "prod"
    purpose     = "terraform-state"
  }

  versioning {
    enabled = true
  }

  soft_delete_policy {
    retention_duration_seconds = 604800
  }

  lifecycle {
    prevent_destroy = true
    # Bootstrap labels appear as effective_labels. Preserve them without an adoption write.
    ignore_changes = [labels]
  }
}
