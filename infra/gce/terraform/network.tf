resource "google_compute_network" "gce" {
  project                 = var.project_id
  name                    = var.network_name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "gce" {
  project                  = var.project_id
  name                     = var.subnet_name
  region                   = var.region
  network                  = google_compute_network.gce.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true
}

resource "google_compute_firewall" "edge_upstreams" {
  project   = var.project_id
  name      = "${var.instance_name}-allow-edge-upstreams"
  network   = google_compute_network.gce.name
  direction = "INGRESS"

  source_ranges           = [var.edge_source_cidr]
  target_service_accounts = [google_service_account.runtime.email]

  allow {
    protocol = "tcp"
    ports = [
      tostring(var.web_upstream_port),
      tostring(var.api_upstream_port),
    ]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_firewall" "iap_ssh" {
  project   = var.project_id
  name      = "${var.instance_name}-allow-iap-ssh"
  network   = google_compute_network.gce.name
  direction = "INGRESS"

  source_ranges           = [var.iap_ssh_source_range]
  target_service_accounts = [google_service_account.runtime.email]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}
