resource "google_secret_manager_secret" "production" {
  for_each = local.production_secret_ids

  project   = var.project_id
  secret_id = each.value

  labels = {
    application = "strayhub"
    environment = "prod"
    phase       = "e2"
  }

  replication {
    auto {}
  }

  lifecycle {
    prevent_destroy = true
    # Imported operator labels appear as effective_labels. Preserve them without an adoption write.
    ignore_changes = [labels]
  }
}

resource "google_secret_manager_secret_iam_member" "runtime" {
  for_each = local.production_secret_ids

  project   = var.project_id
  secret_id = google_secret_manager_secret.production[each.value].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = local.runtime_service_account
}
