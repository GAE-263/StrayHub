resource "google_storage_bucket" "private" {
  project                     = var.project_id
  name                        = var.gcs_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = local.labels

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }

    condition {
      age            = 1
      matches_prefix = ["temporary/"]
    }
  }
}

resource "google_storage_bucket_iam_member" "runtime" {
  for_each = toset(["api", "worker"])

  bucket = google_storage_bucket.private.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.runtime[each.value].email}"
}

resource "google_service_account_iam_member" "api_signed_url" {
  service_account_id = google_service_account.runtime["api"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.runtime["api"].email}"
}
