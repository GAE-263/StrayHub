terraform {
  required_version = ">= 1.6.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # T238 前只可使用 `terraform init -backend=false`。
  backend "gcs" {
    prefix = "strayhub/gcp-demo"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  required_services = toset([
    "artifactregistry.googleapis.com",
    "cloudkms.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
  ])

  labels = {
    app         = "strayhub"
    environment = "gcp-demo"
    managed_by  = "terraform"
  }

  secret_names = {
    database_url                = var.database_url_secret_name
    database_password           = var.database_password_secret_name
    line_channel_secret         = var.line_channel_secret_name
    line_channel_access_token   = var.line_channel_access_token_secret_name
    auth_jwt_active_private_key = var.auth_jwt_active_private_key_secret_name
    auth_jwt_active_public_key  = var.auth_jwt_active_public_key_secret_name
    animal_confirmation_secret  = var.animal_confirmation_secret_name
  }
}

resource "google_project_service" "required" {
  for_each = local.required_services

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

data "google_secret_manager_secret" "runtime" {
  for_each = local.secret_names

  project   = var.project_id
  secret_id = each.value
}
