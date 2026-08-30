output "instance_name" {
  value = google_compute_instance.gce.name
}

output "instance_zone" {
  value = google_compute_instance.gce.zone
}

output "static_ip" {
  value = google_compute_address.gce.address
}

output "service_account_email" {
  value = google_service_account.runtime.email
}

output "network_name" {
  value = google_compute_network.gce.name
}

output "subnet_name" {
  value = google_compute_subnetwork.gce.name
}

output "machine_type" {
  value = google_compute_instance.gce.machine_type
}

output "boot_disk_type" {
  value = var.boot_disk_type
}

output "boot_disk_size_gb" {
  value = var.boot_disk_size_gb
}
