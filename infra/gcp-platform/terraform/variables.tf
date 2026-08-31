variable "project_id" {
  description = "Approved GCP project containing the retained StrayHub platform resources."
  type        = string

  validation {
    condition     = var.project_id == "canvas-primacy-502703-k1"
    error_message = "PLATFORM_TERRAFORM is pinned to the reviewed production project."
  }
}

variable "region" {
  description = "Region of the retained KMS and backup resources."
  type        = string
  default     = "asia-east1"

  validation {
    condition     = var.region == "asia-east1"
    error_message = "PLATFORM_TERRAFORM is pinned to the reviewed asia-east1 resources."
  }
}
