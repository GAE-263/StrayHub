data "google_compute_image" "ubuntu_lts" {
  project = var.ubuntu_image_project
  family  = var.ubuntu_image_family
}

resource "google_compute_address" "gce" {
  project      = var.project_id
  name         = var.address_name
  region       = var.legacy_region
  address_type = "EXTERNAL"
  network_tier = "PREMIUM"
  description  = "Reserved IPv4 for the canonical StrayHub GCE edge"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_compute_address" "us_central1" {
  project      = var.project_id
  name         = var.address_name
  region       = var.region
  address_type = "EXTERNAL"
  network_tier = "PREMIUM"
  description  = "Reserved IPv4 for the canonical StrayHub GCE edge"
}

resource "google_compute_instance" "gce" {
  project                   = var.project_id
  name                      = var.instance_name
  zone                      = var.legacy_zone
  machine_type              = var.machine_type
  allow_stopping_for_update = true
  can_ip_forward            = false
  deletion_protection       = false
  labels                    = local.labels

  boot_disk {
    auto_delete = true

    initialize_params {
      image = data.google_compute_image.ubuntu_lts.self_link
      size  = var.boot_disk_size_gb
      type  = var.boot_disk_type
      labels = merge(local.labels, {
        purpose = "runtime-host"
      })
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.gce.id

    access_config {
      nat_ip       = google_compute_address.gce.address
      network_tier = "PREMIUM"
    }
  }

  service_account {
    email  = google_service_account.runtime.email
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  metadata = {
    enable-oslogin         = "TRUE"
    block-project-ssh-keys = "TRUE"
  }

  metadata_startup_script = templatefile("${path.module}/scripts/bootstrap-host.sh.tftpl", {
    swap_size_gb = var.swap_size_gb
  })

  shielded_instance_config {
    enable_integrity_monitoring = true
    enable_secure_boot          = true
    enable_vtpm                 = true
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    provisioning_model  = "STANDARD"
  }

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = var.admin_access_mode == "iap"
      error_message = "Only IAP-based SSH is accepted."
    }
  }
}

resource "google_compute_snapshot" "gce_us_central1_migration" {
  project           = var.project_id
  name              = var.migration_snapshot_name
  source_disk       = google_compute_instance.gce.boot_disk[0].source
  zone              = var.legacy_zone
  storage_locations = [var.region]
  description       = "Stopped-disk migration snapshot from asia-east1 to us-central1"
  labels            = local.labels

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_compute_instance" "us_central1" {
  project                   = var.project_id
  name                      = var.instance_name
  zone                      = var.zone
  machine_type              = var.machine_type
  allow_stopping_for_update = true
  can_ip_forward            = false
  deletion_protection       = false
  labels                    = local.labels

  boot_disk {
    auto_delete = true

    initialize_params {
      snapshot = google_compute_snapshot.gce_us_central1_migration.self_link
      size     = var.boot_disk_size_gb
      type     = var.boot_disk_type
      labels = merge(local.labels, {
        purpose = "runtime-host"
      })
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.us_central1.id

    access_config {
      nat_ip       = google_compute_address.us_central1.address
      network_tier = "PREMIUM"
    }
  }

  service_account {
    email  = google_service_account.runtime.email
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  metadata = {
    enable-oslogin         = "TRUE"
    block-project-ssh-keys = "TRUE"
  }

  metadata_startup_script = templatefile("${path.module}/scripts/bootstrap-host.sh.tftpl", {
    swap_size_gb = var.swap_size_gb
  })

  shielded_instance_config {
    enable_integrity_monitoring = true
    enable_secure_boot          = true
    enable_vtpm                 = true
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    provisioning_model  = "STANDARD"
  }

  lifecycle {
    precondition {
      condition     = var.admin_access_mode == "iap"
      error_message = "Only IAP-based SSH is accepted in E1."
    }
  }
}
