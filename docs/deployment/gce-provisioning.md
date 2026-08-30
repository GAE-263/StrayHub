# Canonical GCE Provisioning Contract

Status: Phase E1 accepted after controlled bootstrap-idempotency replacement

## Approved target and ownership

The reviewed target is project `canvas-primacy-502703-k1`, region `asia-east1`, zone
`asia-east1-b`, operated by the explicitly confirmed account. `infra/gce/terraform/` is the only
source of truth for the canonical GCE host foundation:

- isolated custom VPC `strayhub-gce-vpc` and subnet `strayhub-gce-subnet`;
- old-edge-source-restricted Web/API and IAP-only SSH firewall rules;
- regional reserved IPv4 `strayhub-gce-ip`;
- dedicated metadata identity `strayhub-gce-sa`;
- single VM `strayhub-gce` and its auto-delete boot disk.

Legacy `infra/gcp-demo/terraform/` remains transitional and has separate state. This subtree does
not own or import Cloud Run, Cloud SQL, existing VMs, Artifact Registry, Secret Manager, KMS, GCS,
DNS, certificates, managed-service IAM, application containers, or deployment CI.

The reviewed initial plan applied successfully with seven additions, zero changes, and zero
destroys. The live VM is `RUNNING` at reserved IPv4 `34.81.77.204`; DNS remains unchanged. Terraform
state contains only the seven E1 resources plus the Ubuntu image data source.

## Read-only live inventory and network decision

The E1 inventory found no VM, static IP, custom subnet, service account, or target-name collision in
`asia-east1`. Two unrelated VMs and reserved addresses named `rrapi-20260813`, `nginx-20260820-033352`,
`rr-test`, and `rrapi-nginx` exist in `us-central1` and are outside this plan.

The project default VPC is rejected for StrayHub because it includes broad public SSH, RDP, and TCP
8080 ingress. The plan creates an isolated custom-mode VPC and `10.42.0.0/24` regional subnet instead
of modifying those rules. No peering, NAT, load balancer, private-service connection, or IPv6 path is
part of E1.

Compute, Storage, Artifact Registry, OS Login, logging, and monitoring APIs are enabled. IAM,
Secret Manager, Cloud KMS, and Cloud SQL Admin were not listed as enabled during inventory. E1 does
not enable APIs; required API enablement must be a separate reviewed mutation before apply.

## VM, disk, and operating system

The Demo/PoC baseline is one `e2-medium` VM (2 vCPU, 4 GiB memory) plus a persistent 2 GiB swap file.
It is intended for low-volume Next.js, FastAPI, Worker, PostgreSQL, and MinIO operation. The
accepted tradeoff is a single-machine SPOF, limited headroom, and maintenance downtime.

The VM uses a 30 GiB `pd-balanced` boot disk for mixed database, object, Docker-layer, and log I/O.
It uses no local SSD. The disk auto-deletes with the E1 VM; later off-VM GCS backup acceptance is
therefore mandatory before production data is entrusted to it. The verified OS family is
`ubuntu-2404-lts-amd64` from `ubuntu-os-cloud`.

## Static IP, firewall, and administration

The regional external IPv4 is reserved separately and attached to the VM. DNS and LINE endpoints do
not change in E1. Firewall rules target only the dedicated service account:

- `34.10.249.63/32` to TCP 3000 and 8080 for the old edge's Web/API upstream access;
- Google IAP TCP forwarding `35.235.240.0/20` to TCP 22.

There is no public 22, 80, or 443 rule and no ingress for PostgreSQL or MinIO. Web/API ports are not
world-open.
OS Login is enabled and project SSH keys are blocked. An administrator still needs the separately
reviewed OS Login key and IAP permissions; Terraform does not grant project IAM or manage profile
keys.

Phase E4 live acceptance replaced the original public 80/443 rule with only
`34.10.249.63/32` to TCP 3000/8080. The old edge is the sole public TLS endpoint. Docker DNAT on the
application VM requires the repo-owned `/etc/sysctl.d/99-strayhub-network.conf`, containing only
`net.ipv4.ip_forward=1`; it persisted across the accepted reboot without custom firewall/NAT rules.

## Identity and ADC

The VM receives `strayhub-gce-sa` with the broad `cloud-platform` OAuth scope and no JSON key. IAM,
not OAuth scope, remains the authorization boundary. E1 creates no role bindings. Later reviews must
grant Secret Accessor per secret, KMS Encrypter/Decrypter on the exact CryptoKey, and GCS Object
Creator/Viewer on the exact backup bucket before live managed-service acceptance.

## Host bootstrap

The startup template installs Docker Engine, the Compose plugin, CA/curl/basic package tooling, and
unattended security updates. It creates the non-root `strayhub` operator and these protected paths:

```text
/opt/strayhub/{compose,config}              0750 strayhub:strayhub
/var/lib/strayhub/{postgres,minio}          0750 strayhub:strayhub
/var/lib/strayhub/{secrets,backups}         0700 strayhub:strayhub
/var/log/strayhub                           0750 strayhub:strayhub
```

Secret files later staged beneath the secret directory remain `0600`. Membership in the Docker
group is intentionally accepted for the single operator but is root-equivalent access and must not
be treated as a sandbox. The bootstrap persists `/swapfile` in `/etc/fstab`, uses mode `0600`, and
sets `vm.swappiness=10`. It deploys no repository, configuration, secret, or application container.

## Apply and replacement evidence

IAP administration, Ubuntu 24.04, the `e2-medium` shape, 30 GiB `pd-balanced` disk, Docker 29.7.2,
Compose v5.5.0, the hello-world smoke test, metadata service-account identity, protected directory
modes, 2 GiB swap, outbound Docker Registry connectivity, and the intended listening/firewall
boundary passed.

The initial reset exposed an E1 defect: `gpg --dearmor` attempted to prompt before overwriting the
existing Docker keyring, so the guest runner logged exit status 2. The source correction uses
non-interactive `gpg --batch --yes`. After confirming the host contained no application, database,
MinIO, secret, backup, Docker volume, or production data, the separately approved corrective saved
plan replaced only `google_compute_instance.gce` with one add, zero changes, and one destroy. The
reserved IP, VPC, subnet, firewall rules, and service account were not replaced.

The replacement changed instance ID `5710279376629586026` to `5310649467353876523` while preserving
IPv4 `34.81.77.204`. Its first metadata startup run exited zero. An explicit second execution of the
same rendered metadata script also exited zero, left exactly one swap fstab entry and one Docker
repository entry, and preserved healthy Docker/Compose and protected paths. One post-replacement
reset produced another startup exit zero and preserved the IP, Docker, Compose, swap, filesystem,
and ADC service-account identity. The final Terraform plan reports no changes.

## Terraform workflow

Run the read-only collision and identity preflight first:

```bash
infra/gce/scripts/gce-terraform-preflight.sh \
  --account b97502027@gmail.com \
  --project canvas-primacy-502703-k1 \
  --region asia-east1 \
  --zone asia-east1-b
```

The bootstrap plan uses ignored local state because no remote backend is approved:

```bash
terraform -chdir=infra/gce/terraform init
terraform -chdir=infra/gce/terraform fmt -recursive -check
terraform -chdir=infra/gce/terraform validate
terraform -chdir=infra/gce/terraform plan \
  -var='project_id=canvas-primacy-502703-k1' \
  -out=terraform.tfplan
terraform -chdir=infra/gce/terraform show terraform.tfplan
```

The initial saved plan was applied only after the identity, collision, and 7/0/0 gates passed. The
corrective replacement was applied only after its disposable-state and exact 1/0/1 gates passed.
Before any later production apply, approve a dedicated remote backend, repeat collision checks,
resolve API enablement, and review exact costs/quotas.

## Verification and rollback contract

E1 verification must include VM `RUNNING`, attached address and service account, IAP administration,
outbound connectivity, Docker/Compose, metadata identity without printing a token, swap and host
paths, and one reboot with IP/Docker/swap/path persistence plus a successful repeat bootstrap. It
must not deploy StrayHub.

Rollback is isolated: destroy only resources present in the dedicated GCE state after reviewing a
destroy plan. VM deletion auto-deletes its boot disk; static-IP release is explicit. Never target
legacy Cloud Run, Cloud SQL, default VPC resources, or `infra/gcp-demo` state. No production data or
backup exists on the accepted VM yet.

Approximate resource classes are one `e2-medium`, one 30 GiB `pd-balanced` disk, one reserved
external IPv4, and network egress as used. This is not an exact billing estimate.

E1-time deferred record: E2 live Secret Manager/KMS/GCS acceptance, E3 systemd supervision, and E4
single-edge live routing are now accepted. Full deployment acceptance/rollback remains Phase E5;
Phase F legacy cleanup and CI replacement remain deferred.
