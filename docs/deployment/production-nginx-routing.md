# Production nginx Single-Origin Routing

Status: Phase B2 verified

The canonical GCE Compose runtime uses `nginx:1.27.5-alpine` as its only host-published service.
Phase B2 verifies this boundary over HTTP on an isolated local port; it does not implement TLS,
DNS, firewall policy, or a real GCE deployment.

## Route table

| Browser path | Compose target | Path handling |
| --- | --- | --- |
| `/healthz` | `api:8080` | Preserved exactly |
| `/v1` and `/v1/*` | `api:8080` | Preserved exactly; `proxy_pass` has no URI suffix |
| `/v1/line/webhook` | `api:8080` | Structurally routed only; no real LINE request is sent |
| `/` and every other path | `web:8080` | Next.js owns pages, assets, and predictable 404s |
| `/volunteer-application` | `web:8080` | LIFF-compatible Web route; no LINE behavior changes |

This is one browser origin: `/` and `/v1/...` share the nginx host. Browser code can continue using
relative `/v1` URLs without CORS. Next.js server-side code retains the private
`API_BASE_URL=http://api:8080` path. There is no production HMR/WebSocket route, MinIO route, or
PostgreSQL route.

## Exposure boundary

Only nginx publishes a host port. `B2_NGINX_HOST_PORT` defaults to `8088` in the synthetic
verification template, so local checks use `http://127.0.0.1:8088`. Web, API, PostgreSQL, MinIO, and
Worker have no host-published ports. nginx reaches only `web:8080` and `api:8080` through Compose
DNS; it never proxies to loopback or `host.docker.internal`.

Port `8088` is production-like local verification only. A real GCE ingress will publish nginx on
ports 80/443 after the separately reviewed DNS, firewall, and TLS work is complete.

The nginx configuration is mounted read-only at `/etc/nginx/conf.d/default.conf`. Preflight renders
Compose and runs the selected nginx image's own `nginx -t` against that exact file. The syntax-only
container maps the Compose DNS names to loopback solely so nginx can resolve its upstream names while
parsing; it does not send traffic or change the production proxy targets.

## Proxy policy

nginx forwards `Host`, `X-Real-IP`, `X-Forwarded-For`, and `X-Forwarded-Proto`. The standard access
log does not include authorization headers or secrets. No explicit proxy timeout override is added
because the repository has no evidence requiring one.

`client_max_body_size 1m` matches the existing browser-facing Next.js API proxy limit of 1,048,576
bytes. This is a temporary operational ceiling, not a new product contract. Revisit it when a
canonical media-upload limit is defined; request bodies must not be unlimited.

## Verification and current limitations

Use the isolated Compose project `strayhub-b2-verify`: run the one-shot migration, start the normal
runtime, and make HTTP checks only through nginx. Verify `/`, `/healthz`,
`/v1/public/volunteer-organizations`, and `/volunteer-application`. A non-POST request to
`/v1/line/webhook` may be used only to prove that nginx reaches FastAPI and preserves the route; it
must not contain a LINE payload or signature.

Next is Phase B3 backup/restore design and verification. Deferred beyond Phase B2: its implementation,
TLS and certificate renewal, DNS, real GCE provisioning, firewall policy, systemd, live Secret
Manager wiring, functional KMS verification, replacement deployment CI, Terraform state migration,
and legacy removal.
