provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

locals {
  labels = {
    application = "strayhub"
    environment = var.environment
    managed_by  = "terraform"
    phase       = "e1"
  }
}
