output "instance_name" {
  value = google_compute_instance.us_central1.name
}

output "instance_zone" {
  value = google_compute_instance.us_central1.zone
}

output "static_ip" {
  value = google_compute_address.us_central1.address
}

output "legacy_instance_zone" {
  value = google_compute_instance.gce.zone
}

output "legacy_static_ip" {
  value = google_compute_address.gce.address
}

output "migration_snapshot" {
  value = google_compute_snapshot.gce_us_central1_migration.name
}

output "service_account_email" {
  value = google_service_account.runtime.email
}

output "network_name" {
  value = google_compute_network.gce.name
}

output "subnet_name" {
  value = google_compute_subnetwork.us_central1.name
}

output "machine_type" {
  value = google_compute_instance.us_central1.machine_type
}

output "boot_disk_type" {
  value = var.boot_disk_type
}

output "boot_disk_size_gb" {
  value = var.boot_disk_size_gb
}

output "web_upstream_port" {
  value = var.web_upstream_port
}

output "api_upstream_port" {
  value = var.api_upstream_port
}
