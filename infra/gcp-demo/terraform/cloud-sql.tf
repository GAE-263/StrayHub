resource "google_compute_network" "demo" {
  project                 = var.project_id
  name                    = "${var.name_prefix}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_global_address" "private_service_access" {
  project       = var.project_id
  name          = "${var.name_prefix}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.demo.id
}

resource "google_service_networking_connection" "private_service_access" {
  network                 = google_compute_network.demo.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_access.name]
}

resource "google_sql_database_instance" "demo" {
  project             = var.project_id
  name                = "${var.name_prefix}-postgres"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = false

  settings {
    tier              = var.database_tier
    disk_type         = "PD_SSD"
    disk_size         = var.database_disk_size_gb
    availability_type = "ZONAL"

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 3
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.demo.id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    user_labels = local.labels
  }

  depends_on = [google_service_networking_connection.private_service_access]
}

resource "google_sql_database" "crm" {
  project  = var.project_id
  name     = var.database_name
  instance = google_sql_database_instance.demo.name
}

resource "google_sql_user" "runtime" {
  project  = var.project_id
  name     = var.database_runtime_user
  instance = google_sql_database_instance.demo.name
  password = var.database_password
}

resource "google_sql_user" "migration" {
  project  = var.project_id
  name     = var.database_migration_user
  instance = google_sql_database_instance.demo.name
  password = var.migration_database_password
}
