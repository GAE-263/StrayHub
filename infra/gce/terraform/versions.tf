terraform {
  required_version = ">= 1.6.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # E1 uses isolated local bootstrap state. Resolve a dedicated remote backend before apply.
  backend "local" {
    path = "terraform.tfstate"
  }
}
