# Production nginx Single-Origin Routing

Status: Phase B4 TLS edge verified locally

The canonical GCE Compose runtime uses `nginx:1.27.5-alpine` as its only host-published service.
Phase B4 publishes synthetic local HTTP/HTTPS ports; real production maps TCP 80/443 after the
static-IP, DNS, firewall, and certificate gates in `tls-dns-firewall.md` pass.

## Route table

| Public path | Behavior or target | Path handling |
| --- | --- | --- |
| HTTP `/.well-known/acme-challenge/*` | Dedicated ACME webroot | No redirect; missing file is 404 |
| Every other HTTP path | 308 HTTPS redirect | Host, path, and query preserved |
| HTTPS `/healthz` | `api:8080` | Preserved exactly |
| HTTPS `/v1` and `/v1/*` | `api:8080` | Preserved exactly; no URI suffix |
| HTTPS `/v1/line/webhook` | `api:8080` | Structural route only; no real LINE request |
| HTTPS `/` and every other path | `web:8080` | Next.js owns pages, assets, and 404s |
| HTTPS `/volunteer-application` | `web:8080` | Canonical LIFF-compatible Web route |

This remains one browser origin. Browser code uses relative `/v1` URLs, while Next.js server-side
code retains `API_BASE_URL=http://api:8080`. There is no production HMR route, MinIO route, database
route, or public internal service.

## Exposure and proxy policy

Only nginx publishes ports. The synthetic template maps HTTP 8088 and HTTPS 8443; production maps
the same container listeners to host 80 and 443. Web, API, PostgreSQL, MinIO, Worker, and the MinIO
console remain private. nginx reaches `web:8080` and `api:8080` only through Compose DNS.

HTTPS forwards `Host`, `X-Real-IP`, `X-Forwarded-For`, and a fixed
`X-Forwarded-Proto: https`. The `client_max_body_size 1m` policy is identical in HTTP and HTTPS
blocks. HTTP has no application proxy, so redirect loops cannot originate at the application.
Conservative response headers are documented in the edge contract; HSTS is deliberately deferred.

Preflight generates ignored JWT and self-signed TLS verification material, renders Compose, and runs
the selected nginx image's `nginx -t` against the mounted config/certificate/webroot. The isolated
`strayhub-b4-final` drill must test redirect, HTTPS Web/API/LIFF routing, structural webhook routing,
and ACME challenge bytes without sending real LINE traffic. `curl -k` is local verification only.

The completed isolated drill returned 308 for HTTP, served the synthetic ACME probe without a
redirect, and returned 200 for HTTPS `/`, `/healthz`, `/v1/public/volunteer-organizations`, and
`/volunteer-application`. HTTPS `/v1/line/webhook` GET returned the expected 405 structural proof.
