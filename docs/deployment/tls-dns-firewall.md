# TLS, DNS, and Firewall Edge Contract

Status: Phase B4 local TLS edge verified; real edge changes deferred

## Edge topology and exposure

The canonical production edge is a reserved GCE static external IP with one public hostname. DNS
points that hostname directly to the VM; nginx on the VM is the only public Compose service:

```text
Internet -> reserved GCE static IP -> TCP 80/443 -> nginx
                                                |-> /healthz and /v1/* -> API
                                                `-> all other paths -> Web
```

The firewall allows inbound TCP 80 and 443 only for application traffic. It must not expose Web
3000/3001, API 8000/8001/8080, PostgreSQL 5432, MinIO 9000/9001, or Worker ports. SSH must use a
controlled administrator path or restricted source ranges; broad `0.0.0.0/0` SSH is not accepted by
this contract. B4 documents this policy but makes no GCP firewall mutation.

## DNS and static IP

Until an approved production domain exists, examples use `strayhub.example.com`. The deployment has
one canonical public hostname. `www` is unsupported until an explicit redirect and certificate SAN
are approved. An A record points to the reserved static external IPv4 address; add an AAAA record
only if the VM has a deliberately configured static IPv6 path and matching firewall policy.

Reserve the external address before DNS cutover. DNS must resolve to that stable address before
certificate issuance. This stability also protects the LINE webhook and LIFF endpoint references.
Phase E owns static-IP provisioning and DNS evidence; B4 does not create or modify records.

The eventual public URL shapes are:

- `https://<canonical-host>/v1/line/webhook`
- `https://<canonical-host>/volunteer-application`

The LIFF endpoint must be HTTPS. No LINE Developers setting or real webhook is changed in B4.

## TLS and ACME strategy

nginx terminates TLS on the single VM. Host-level Certbot obtains a Let's Encrypt certificate using
HTTP-01 and stores its state under `/etc/letsencrypt`. This avoids an external HTTPS load balancer
and a long-running Certbot container, matching the selected low-cost single-VM architecture.

The certificate must use Certbot certificate name `strayhub`, producing:

```text
/etc/letsencrypt/live/strayhub/fullchain.pem
/etc/letsencrypt/live/strayhub/privkey.pem
```

Compose mounts the entire Certbot state read-only at `/etc/letsencrypt` so archive symlink rotation
continues to work. The host ACME webroot is mounted read-only at `/var/www/certbot`. Only
`/.well-known/acme-challenge/` is served over HTTP; directory listing is disabled and missing files
return 404. Every other HTTP request returns 308 to the same host and URI over HTTPS. The HTTPS block
keeps the B2 `1m` body limit and routes unchanged, preserves `Host`, appends `X-Forwarded-For`, and
sets `X-Forwarded-Proto: https`.

A production issuance command is intentionally not executed in B4. After DNS and firewall gates,
an operator may use the host package's equivalent of:

```bash
certbot certonly --webroot --webroot-path /var/lib/strayhub/acme-webroot \
  --cert-name strayhub -d <canonical-host>
```

## Renewal and failure policy

The production host performs a daily renewal check. The future Phase E scheduler runs `certbot
renew` and reloads nginx only from a successful deploy hook, for example `docker compose ... exec -T
nginx nginx -s reload`. B4 records the command contract but adds no cron job, systemd unit, or timer.

Failed issuance leaves HTTPS unavailable and blocks production cutover; it never enables plaintext
application traffic. Failed renewal keeps the existing valid certificate, emits an operator-visible
error, and must alert before expiry. A broken or expired certificate is an incident: fix issuance and
reload safely, without replacing it with a self-signed certificate or falling back to HTTP.

## Local verification certificate

`infra/gce/scripts/generate-verification-tls-cert.sh` creates a self-signed RSA certificate at
runtime for `b4-verification.local`, `localhost`, and `127.0.0.1`. It reuses a valid pair, repairs a
missing/invalid pair, and supports `--force`. The private key is mode `0600`, the certificate `0644`,
and both remain beneath Git- and Docker-ignored `infra/gce/verification/generated/`.

The synthetic Compose env publishes nginx on local ports 8088 and 8443 and mounts this verification
tree in the same shape as Certbot state. `curl -k` is acceptable only for this self-signed isolated
drill; production clients must validate the public CA chain normally.

The isolated `strayhub-b4-final` drill passed HTTP 308 redirect, exact ACME challenge bytes, HTTPS
Web root, API health, public versioned API, and Volunteer LIFF route. A GET to the LINE webhook
returned the expected 405 through nginx, proving structural path ownership without a LINE payload.
The running container passed `nginx -t`; Compose published only nginx's verification ports.

## Headers and trusted proxies

B4 enables conservative `X-Content-Type-Options: nosniff` and
`Referrer-Policy: strict-origin-when-cross-origin`. HSTS and frame policy are deferred until the real
hostname/TLS deployment and LIFF embedded-browser compatibility are proven. nginx supplies forwarded
headers, but Phase E must explicitly constrain Uvicorn's trusted proxy source to the Compose nginx
boundary; global client-IP trust must not be weakened.

Deferred: real certificate issuance, DNS/static-IP/firewall changes, systemd/cron scheduling, real
GCE, load balancers, live Secret Manager/KMS/GCS wiring, deployment CI replacement, Terraform state
migration, and legacy deletion.
