variable "project_id" {
  description = "GCP Demo Project ID; never commit the value."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id 必須是 6～30 字元的小寫 GCP Project ID。"
  }
}

variable "region" {
  description = "GCP region for the Demo resources."
  type        = string
  default     = "asia-east1"
}

variable "name_prefix" {
  description = "Globally unique, lowercase resource prefix."
  type        = string
  default     = "strayhub-demo"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,24}$", var.name_prefix))
    error_message = "name_prefix 只能包含小寫字母、數字與連字號，長度 3～25。"
  }
}

variable "gcs_bucket_name" {
  description = "Globally unique private GCS bucket name."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$", var.gcs_bucket_name))
    error_message = "gcs_bucket_name 必須符合 GCS bucket naming rules。"
  }
}

variable "artifact_repository_id" {
  description = "Artifact Registry repository ID."
  type        = string
  default     = "strayhub-demo"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,49}$", var.artifact_repository_id))
    error_message = "artifact_repository_id 格式無效。"
  }
}

variable "api_image" {
  description = "Immutable FastAPI image reference produced by CI."
  type        = string
}

variable "web_image" {
  description = "Immutable Next.js image reference produced by CI."
  type        = string
}

variable "worker_image" {
  description = "Immutable Worker image reference produced by CI."
  type        = string
}

variable "database_tier" {
  description = "Cloud SQL tier for the fictional Demo."
  type        = string
  default     = "db-f1-micro"
}

variable "database_disk_size_gb" {
  description = "Cloud SQL disk size."
  type        = number
  default     = 10

  validation {
    condition     = var.database_disk_size_gb >= 10
    error_message = "database_disk_size_gb 不得小於 10。"
  }
}

variable "database_name" {
  description = "CRM database name."
  type        = string
  default     = "strayhub"
}

variable "database_runtime_user" {
  description = "Cloud SQL runtime role name."
  type        = string
  default     = "strayhub_runtime"
}

variable "database_migration_user" {
  description = "Cloud SQL migration role name."
  type        = string
  default     = "strayhub_migration"
}

variable "database_password" {
  description = "Sensitive runtime database password, injected outside Git."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.database_password) >= 24
    error_message = "database_password 必須至少 24 字元，且不得提交至版本庫。"
  }
}

variable "migration_database_password" {
  description = "Sensitive migration database password, injected outside Git."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.migration_database_password) >= 24
    error_message = "migration_database_password 必須至少 24 字元，且不得提交至版本庫。"
  }
}

variable "domain" {
  description = "Optional HTTPS domain used to form LIFF and webhook references."
  type        = string
  default     = ""

  validation {
    condition     = var.domain == "" || can(regex("^[a-z0-9.-]+$", var.domain))
    error_message = "domain 只能包含小寫字母、數字、點與連字號。"
  }
}

variable "liff_id" {
  description = "Fictional or controlled LIFF ID reference."
  type        = string
  default     = "gcp-demo-liff"
}

variable "github_repository" {
  description = "GitHub owner/repository allowed to use the OIDC provider."
  type        = string

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repository))
    error_message = "github_repository 必須是 owner/repository。"
  }
}

variable "database_url_secret_name" {
  description = "Existing Secret Manager secret containing DATABASE_URL."
  type        = string
  default     = "database-url"
}

variable "database_password_secret_name" {
  description = "Existing Secret Manager secret containing the runtime database password."
  type        = string
  default     = "database-password"
}

variable "line_channel_secret_name" {
  description = "Existing Secret Manager secret containing LINE channel secret."
  type        = string
  default     = "line-channel-secret"
}

variable "line_channel_access_token_secret_name" {
  description = "Existing Secret Manager secret containing LINE access token."
  type        = string
  default     = "line-channel-access-token"
}

variable "auth_jwt_active_private_key_secret_name" {
  description = "Existing Secret Manager secret containing the active JWT private key."
  type        = string
  default     = "auth-jwt-active-private-key"
}

variable "auth_jwt_active_public_key_secret_name" {
  description = "Existing Secret Manager secret containing the active JWT public key."
  type        = string
  default     = "auth-jwt-active-public-key"
}

variable "animal_confirmation_secret_name" {
  description = "Existing Secret Manager secret containing the animal confirmation secret."
  type        = string
  default     = "animal-confirmation-secret"
}
