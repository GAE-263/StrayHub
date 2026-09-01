data "google_compute_network" "default" {
  project = var.project_id
  name    = "default"
}

resource "google_compute_network_peering" "default_to_strayhub" {
  name         = "default-to-strayhub"
  network      = data.google_compute_network.default.self_link
  peer_network = google_compute_network.gce.self_link

  import_custom_routes = false
  export_custom_routes = false
}

resource "google_compute_network_peering" "strayhub_to_default" {
  name         = "strayhub-to-default"
  network      = google_compute_network.gce.self_link
  peer_network = data.google_compute_network.default.self_link

  import_custom_routes = false
  export_custom_routes = false
}
