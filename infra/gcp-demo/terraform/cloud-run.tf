resource "google_cloud_run_v2_service" "web" {
  project             = var.project_id
  name                = "${var.name_prefix}-web"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false
  labels              = local.labels

  template {
    service_account = google_service_account.runtime["next"].email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.web_image

      ports {
        container_port = 8080
      }

      env {
        name  = "NEXT_PUBLIC_API_BASE_URL"
        value = "https://${var.domain}"
      }

      env {
        name  = "LIFF_ID"
        value = var.liff_id
      }
    }
  }
}

resource "google_cloud_run_v2_service" "api" {
  project             = var.project_id
  name                = "${var.name_prefix}-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false
  labels              = local.labels

  template {
    service_account = google_service_account.runtime["api"].email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.api_image

      ports {
        container_port = 8080
      }

      env {
        name  = "APP_ENV"
        value = "gcp-demo"
      }

      env {
        name  = "GCS_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.private.name
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.runtime["database_url"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "LINE_CHANNEL_SECRET"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.runtime["line_channel_secret"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "LINE_CHANNEL_ACCESS_TOKEN"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.runtime["line_channel_access_token"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "AUTH_JWT_ACTIVE_PRIVATE_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.runtime["auth_jwt_active_private_key"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "AUTH_JWT_ACTIVE_PUBLIC_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.runtime["auth_jwt_active_public_key"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "ANIMAL_CONFIRMATION_SECRET"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.runtime["animal_confirmation_secret"].secret_id
            version = "latest"
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service" "worker" {
  project             = var.project_id
  name                = "${var.name_prefix}-worker"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false
  labels              = local.labels

  template {
    service_account = google_service_account.runtime["worker"].email

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image = var.worker_image

      ports {
        container_port = 8080
      }

      env {
        name  = "APP_ENV"
        value = "gcp-demo"
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.runtime["database_url"].secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.private.name
      }
    }
  }
}

resource "google_cloud_run_v2_job" "migration" {
  project             = var.project_id
  name                = "${var.name_prefix}-migration"
  location            = var.region
  deletion_protection = false
  labels              = local.labels

  template {
    template {
      service_account = google_service_account.runtime["migration"].email
      max_retries     = 1
      timeout         = "1800s"

      containers {
        image   = var.api_image
        command = ["alembic"]
        args    = ["upgrade", "head"]

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = data.google_secret_manager_secret.runtime["database_url"].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "web_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.web.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "api_public_webhook" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
