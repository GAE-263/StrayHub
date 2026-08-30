variable "project_id" {
  description = "Approved GCP project ID. Supply explicitly; do not infer it from gcloud defaults."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid GCP project ID."
  }
}

variable "region" {
  description = "Region for the canonical GCE deployment."
  type        = string
  default     = "asia-east1"
}

variable "zone" {
  description = "Zone for the canonical single VM."
  type        = string
  default     = "asia-east1-b"
}

variable "environment" {
  description = "Non-secret resource label."
  type        = string
  default     = "production"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,31}$", var.environment))
    error_message = "environment must be a safe lowercase label."
  }
}

variable "instance_name" {
  description = "Canonical GCE VM name."
  type        = string
  default     = "strayhub-gce"
}

variable "machine_type" {
  description = "Demo/PoC baseline for nginx, Web, API, Worker, PostgreSQL, and MinIO."
  type        = string
  default     = "e2-medium"
}

variable "boot_disk_size_gb" {
  description = "Balanced persistent boot disk size in GiB."
  type        = number
  default     = 30

  validation {
    condition     = var.boot_disk_size_gb >= 30
    error_message = "boot_disk_size_gb must be at least 30 GiB."
  }
}

variable "boot_disk_type" {
  description = "Persistent disk type for mixed database, object, image, and log I/O."
  type        = string
  default     = "pd-balanced"

  validation {
    condition     = var.boot_disk_type == "pd-balanced"
    error_message = "E1 requires pd-balanced unless a later review changes the contract."
  }
}

variable "ubuntu_image_project" {
  description = "Public image project containing the supported Ubuntu LTS family."
  type        = string
  default     = "ubuntu-os-cloud"
}

variable "ubuntu_image_family" {
  description = "Supported Ubuntu LTS image family verified during E1 inventory."
  type        = string
  default     = "ubuntu-2404-lts-amd64"
}

variable "address_name" {
  description = "Regional reserved external IPv4 name."
  type        = string
  default     = "strayhub-gce-ip"
}

variable "network_name" {
  description = "Isolated custom-mode VPC name."
  type        = string
  default     = "strayhub-gce-vpc"
}

variable "subnet_name" {
  description = "Canonical VM subnet name."
  type        = string
  default     = "strayhub-gce-subnet"
}

variable "subnet_cidr" {
  description = "Private CIDR for the isolated GCE subnet."
  type        = string
  default     = "10.42.0.0/24"
}

variable "service_account_id" {
  description = "Dedicated VM service account ID; no key resource is created."
  type        = string
  default     = "strayhub-gce-sa"
}

variable "admin_access_mode" {
  description = "E1 admin ingress mode. Only IAP TCP forwarding is accepted."
  type        = string
  default     = "iap"

  validation {
    condition     = var.admin_access_mode == "iap"
    error_message = "E1 permits only IAP-based SSH."
  }
}

variable "iap_ssh_source_range" {
  description = "Google IAP TCP forwarding source range."
  type        = string
  default     = "35.235.240.0/20"
}

variable "swap_size_gb" {
  description = "Persistent swap-file size configured by the host bootstrap."
  type        = number
  default     = 2

  validation {
    condition     = var.swap_size_gb == 2
    error_message = "E1's e2-medium baseline uses a 2 GiB swap file."
  }
}
