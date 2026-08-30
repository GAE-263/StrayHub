# TLS, DNS, and Firewall Edge Contract

Status: Phase E4 single-edge live cutover accepted

## Edge topology and exposure

The canonical public edge is the existing nginx VM at `34.10.249.63`. DNS and the valid Let's
Encrypt certificate for `strayhub.enadv.quest` remain on that host. The application VM at
`34.81.77.204` no longer runs nginx:

```text
Internet -> strayhub.enadv.quest -> old VM nginx 34.10.249.63 (TLS + routing)
                                      |-> 34.81.77.204:8080 (API)
                                      `-> 34.81.77.204:3000 (Web)
```

The old edge alone accepts public TCP 80/443. On the new GCE VM, host ports 3000 (Web) and 8080
(API) accept ingress only from `34.10.249.63/32`. PostgreSQL 5432 and MinIO 9000/9001 remain
unpublished. SSH remains IAP-only from `35.235.240.0/20`; broad `0.0.0.0/0` SSH is forbidden.

## DNS and static IP

The approved canonical hostname is `strayhub.enadv.quest`, and its existing DNS A record continues
to point to the old edge at `34.10.249.63`. E4 makes no DNS mutation. `www` remains unsupported and
no AAAA record is added.

The new VM keeps its reserved external IP `34.81.77.204` solely as the source-restricted application
upstream and IAP administration target. It is not the canonical DNS/TLS endpoint.

The eventual public URL shapes are:

- `https://strayhub.enadv.quest/v1/line/webhook`
- `https://strayhub.enadv.quest/volunteer-application`

The hostname is unchanged, so this adjustment changes no LINE webhook, LIFF, or Rich Menu URL.

## TLS and ACME strategy

The old edge nginx terminates TLS using its existing host-level Certbot installation. The accepted
certificate SAN is `strayhub.enadv.quest`; the new GCE VM must not issue or mount a public
certificate.

The existing edge certificate uses:

```text
/etc/letsencrypt/live/strayhub.enadv.quest/fullchain.pem
/etc/letsencrypt/live/strayhub.enadv.quest/privkey.pem
```

No certificate material is mounted into the new application Compose stack. The tracked old-edge
config preserves `/.well-known/acme-challenge/`, redirects other HTTP traffic to HTTPS, keeps the
`1m` body limit, preserves `Host`, appends `X-Forwarded-For`, and sets
`X-Forwarded-Proto: https`.

E4 neither issues nor replaces the certificate.

## Renewal and failure policy

The existing old-edge Certbot mechanism continues to own renewal. Renewal reloads only host nginx;
it never restarts the new application Compose stack.

Failed issuance leaves HTTPS unavailable and blocks production cutover; it never enables plaintext
application traffic. Failed renewal keeps the existing valid certificate, emits an operator-visible
error, and must alert before expiry. A broken or expired certificate is an incident: fix issuance and
reload safely, without replacing it with a self-signed certificate or falling back to HTTP.

## Local verification certificate

`infra/gce/scripts/generate-verification-tls-cert.sh` creates a self-signed RSA certificate at
runtime for `b4-verification.local`, `localhost`, and `127.0.0.1`. It reuses a valid pair, repairs a
missing/invalid pair, and supports `--force`. The private key is mode `0600`, the certificate `0644`,
and both remain beneath Git- and Docker-ignored `infra/gce/verification/generated/`.

The historical B4 synthetic Compose env published nginx on local ports 8088 and 8443 and mounted
this verification tree in the same shape as Certbot state. The selected E4 application Compose no
longer mounts it. `curl -k` is acceptable only for that self-signed isolated drill; production
clients must validate the public CA chain normally.

The historical isolated `strayhub-b4-final` drill passed HTTP 308 redirect, exact ACME challenge bytes, HTTPS
Web root, API health, public versioned API, and Volunteer LIFF route. A GET to the LINE webhook
returned the expected 405 through nginx, proving structural path ownership without a LINE payload.
The running container passed `nginx -t`; Compose published only nginx's verification ports.

## Headers and trusted proxies

The tracked old-edge config enables conservative `X-Content-Type-Options: nosniff` and
`Referrer-Policy: strict-origin-when-cross-origin`. HSTS and frame policy remain deferred pending
explicit LIFF embedded-browser compatibility acceptance. nginx supplies forwarded
headers. Firewall ingress constrains the application upstreams to `34.10.249.63/32`; global
client-IP trust must not be weakened.

The live E4 acceptance passed edge reload, public Web/API/LIFF routes, structural LINE webhook
routing, trusted existing TLS, edge-only upstream firewall behavior, and one application-VM reboot.
Deferred: deployment CI replacement, Terraform state migration, and legacy deletion.
