terraform {
  required_version = ">= 1.6.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  backend "gcs" {
    bucket = "strayhub-platform-tfstate-canvas-primacy-502703-k1"
    prefix = "strayhub/platform"
  }
}
