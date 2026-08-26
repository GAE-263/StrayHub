locals {
  api_roles = toset([
    "roles/cloudsql.client",
    "roles/logging.logWriter",
    "roles/secretmanager.secretAccessor",
    "roles/storage.objectAdmin",
  ])

  worker_roles = toset([
    "roles/cloudsql.client",
    "roles/logging.logWriter",
    "roles/secretmanager.secretAccessor",
    "roles/storage.objectAdmin",
  ])

  next_roles = toset([
    "roles/logging.logWriter",
    "roles/secretmanager.secretAccessor",
  ])

  migration_roles = toset([
    "roles/cloudsql.client",
    "roles/logging.logWriter",
    "roles/secretmanager.secretAccessor",
  ])
}

resource "google_service_account" "runtime" {
  for_each = {
    api       = "FastAPI CRM runtime"
    next      = "Next.js web runtime"
    worker    = "Background Worker runtime"
    migration = "Cloud SQL migration job"
  }

  account_id   = "${var.name_prefix}-${each.key}"
  display_name = each.value
  project      = var.project_id
}

resource "google_project_iam_member" "api" {
  for_each = local.api_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.runtime["api"].email}"
}

resource "google_project_iam_member" "worker" {
  for_each = local.worker_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.runtime["worker"].email}"
}

resource "google_project_iam_member" "next" {
  for_each = local.next_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.runtime["next"].email}"
}

resource "google_project_iam_member" "migration" {
  for_each = local.migration_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.runtime["migration"].email}"
}

resource "google_kms_crypto_key_iam_member" "api_volunteer_pii" {
  crypto_key_id = var.pii_kms_key_name
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.runtime["api"].email}"

  depends_on = [google_project_service.required["cloudkms.googleapis.com"]]
}

resource "google_secret_manager_secret_iam_member" "runtime" {
  for_each = {
    for pair in flatten([
      for service in ["api", "worker", "next"] : [
        for secret in keys(local.secret_names) : {
          key     = "${service}-${secret}"
          service = service
          secret  = secret
        }
      ]
    ]) : pair.key => pair
  }

  project   = var.project_id
  secret_id = data.google_secret_manager_secret.runtime[each.value.secret].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime[each.value.service].email}"
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "${var.name_prefix}-github"
  display_name              = "${var.name_prefix} GitHub Actions"
  description               = "OIDC pool restricted to the configured GitHub repository."
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub Actions OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  attribute_condition = "assertion.repository == '${var.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_project_iam_member" "github_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}
