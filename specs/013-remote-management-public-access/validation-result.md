# Validation Result: Remote Management Public Access

## Phase A — Auth Protection

**Date**: 2026-09-05
**Status**: PASS — T001–T013 complete
**Activation status**: Not activated. `/login` and management routes remain outside the shared
public tunnel.

### Verified behavior

- Account abuse keys use a dedicated HMAC-SHA256 secret and NFKC → trim → casefold normalization;
  authentication lookup still receives the original submitted username.
- PostgreSQL stores only account/IP digests. It atomically serializes absent and existing rows with
  transaction advisory locks.
- Account failures 1–4 return the generic 401 contract. Failure 5 creates a 15-minute lock and
  returns the generic 429 contract with `Retry-After`; a correct password cannot bypass an active
  lock. Expiry at the 15-minute boundary resets the state.
- The source-IP rolling window admits 20 attempts, rejects attempt 21 without inserting another
  event, and recovers after the oldest event expires. Successful login clears only account state.
- Concurrent account/IP tests use real PostgreSQL transactions and deterministic events rather than
  sleeps. A separate SQLAlchemy engine sees persisted lock state, representing worker/process pool
  replacement.
- Direct mode uses the socket peer and ignores forwarding headers. Trusted-proxy mode accepts one
  canonical IPv4/IPv6 value only from the configured loopback gateway metadata header; missing,
  forged, duplicate, or invalid metadata fails closed.
- Unknown and unusable accounts execute one Argon2 verification against a valid fixed dummy hash and
  retain the same outward wrong-credential behavior. This narrows obvious timing differences; it is
  not claimed to be perfectly constant-time.
- Synthetic raw account, password, and IP sentinels were absent from captured application logs. The
  existing centralized logging and audit-redaction regression tests remain green.

### Evidence

- Phase A schema/unit/security/integration/auth targeted matrix: PASS.
- Broader authentication contract, adapter, session, scope, and role regressions: PASS.
- Existing sensitive logging, audit, static-policy, and URL-registry regressions: PASS.
- Acceptance bootstrap and local authentication compatibility: PASS.
- Alembic: one head (`0045_remote_login_abuse`); actual `0045 → 0044 → head` cycle: PASS.
- Ruff lint/format for touched files: PASS.
- Mypy project boundary and all eight touched production modules: PASS.
- `git diff --check`: recorded in final Phase A handoff.

### Scope boundary

At the Phase A checkpoint, no Phase B–E implementation was performed. In particular, Phase A did
not add a management
registry compiler, shared-demo nginx routes, public Host policy, remote session origin, rollback
automation, or public remote-login smoke testing.

## Phase B — Shared Profile Contracts

**Date**: 2026-09-05
**Status**: PASS — T014–T022 implemented and locally validated
**Activation status**: Not activated. Runtime routing, nginx, tunnel launchers, and public exposure
remain unchanged; those begin in Phase C.

### Contract result

- Management registry: 23 effective routes, all carrying explicit FR-004 metadata plus
  `category` and `demo_required`. Platform administration, volunteer PII surfaces, broad API/UI
  patterns, unanchored patterns, malformed paths, unsupported methods/upstreams, and unknown
  security policy values fail closed.
- LINE registry: 25 existing routes are consumed read-only through compatibility metadata. The
  source digest is pinned by a deterministic contract test; the 013 compiler does not copy or
  rewrite LINE route definitions.
- Profiles: `line-only` compiles to 25 routes; `shared-demo-dev` compiles to 48 routes and retains
  the existing bounded Next static/HMR entries; `shared-demo-production` compiles to 46 routes,
  excludes both development entries, and adds exact manifest-proven assets.
- Composition: unknown profiles, registries, exclusions, duplicate IDs, incomplete LINE metadata,
  and overlapping method/path contracts with different upstream or security policy fail closed.
- Host policy: shared profiles require a runtime-only origin. Public origins require exact HTTPS
  authority and reject userinfo, wildcard, path, query, fragment, non-default port, malformed
  authority, and loopback. Loopback HTTP is accepted only with the explicit local-test flag. Host
  comparison is IDNA/case/port normalized and exact.
- Next assets: Next 15 `build-manifest.json` and `app-build-manifest.json` are parsed for the
  allowlisted pages, applicable layouts, shared runtime chunks, JS, and CSS. Source maps,
  `/_next/image`, non-static paths, unlisted pages, unknown internals, and unresolved manifests
  fail closed. No chunk filename is committed as policy.
- RSC: no blanket `_rsc` route exists. The allowlisted page path and its ordinary preserved query
  contract remain the boundary.

### Verification evidence

- Phase B contract/unit matrix: 56 passed; settings regression matrix: 27 passed.
- Real `npm --prefix apps/web run build`: PASS (Next.js 15.5.24, 25 static pages generated).
- Production compiler against the fresh real `.next` manifests: PASS; 29 exact JS/CSS assets
  resolved for the 12 registry route IDs / 13 concrete pages.
- Ruff lint and format for touched Python files: PASS.
- Mypy for the compiler and settings boundary: PASS.
- No actual ngrok hostname is stored; tests use reserved documentation domains only.

### Known boundary and compatibility notes

- The authoritative 012 LINE registry is committed upstream in `9015166`; 013 reads and composes
  that source contract without taking ownership or creating a duplicate allowlist.
- Existing LINE UUID patterns such as `[0-9a-fA-F-]{36}` are preserved as legacy 012 semantics.
  Management patterns require canonical UUID bounds. Tightening LINE patterns is outside Phase B.
- No current registry/profile discrepancy prevented compilation. Runtime deny/allow behavior is
  not claimed here because nginx generation and integration tests belong to Phase C.

## Phase C — Gateway and Helper Integration

**Date**: 2026-09-05
**Status**: PASS — T023–T036 implemented and locally validated
**Activation status**: Not activated. No real public tunnel or remote browser smoke was run; those
remain Phase E and are blocked until the outstanding 012 T008 manual incident actions are complete.

### Gateway and helper result

- `generate_public_tunnel_config.py` consumes the committed 012 LINE registry plus the 013
  management registry/profile compiler and writes nginx and ngrok Traffic Policy only to an
  external runtime temporary directory. The generated nginx config uses exact or anchored bounded
  locations, method and query guards, separate API/web upstreams, exact Host authority for shared
  profiles, suspicious raw-path rejection, and a final 404 with no broad management/API fallback.
- The public nginx log format contains method, normalized path, status, response size, latency and
  request ID only. It excludes query strings, referrer, authorization and body data.
- The ngrok policy removes client-supplied trusted IP/profile/forwarding headers before setting the
  connection-derived client IP, HTTPS scheme and selected shared profile. The installed ngrok
  3.39.9 CLI exposes `--traffic-policy-file`; the policy structure is checked deterministically.
  It was not attached to a live endpoint in this phase.
- `demo-line.sh` and `test_line_local.sh` remain `line-only` by default. Shared access requires
  `--profile shared-demo-production`, `--profile shared-demo-dev`, or the explicit management
  wrapper. Production mode builds and starts Next production before deriving exact static assets;
  dev mode alone retains HMR. Helpers validate origin, compiler output, ngrok config and nginx
  syntax before public startup, and keep generated files under helper-owned temporary directories.

### Backend and frontend result

- FastAPI accepts `X-StrayHub-Public-Profile` only from the configured loopback gateway and only for
  the two known shared profiles. Client body/query values cannot select the profile. Existing bearer
  sessions and refresh requests are rechecked against server-side identity and effective access.
- Shared management permits active `STAFF` and `SHELTER_ADMIN` only. `PLATFORM_ADMIN`, `VOLUNTEER`
  and expired/disabled access are rejected without changing their existing local/private behavior.
  No session-origin field, migration or rollback lifecycle from Phase D was added.
- `/v1/auth/me` returns a nullable server-derived `public_exposure_profile`. The frontend does not
  read URL or storage to infer it. Shared profiles show only dashboard, animals, reports, care
  calendar and AI review navigation, and hide report correction/archive plus care mutation controls.
  Management children are not rendered until `/me` has loaded, preventing a pre-hydration flash of
  those controls.

### Verification evidence

- Pre-commit regression repair: three Phase A API tests initially failed because their injected
  login service doubles had not adopted the Phase C `public_exposure_profile` keyword. The doubles
  now accept and explicitly assert the local/private `None` value; no production code or auth
  behavior changed. The original file passes 3/3, the Phase A auth suite passes 34/34, and the
  Phase B/C gateway, role, Host and LINE matrix passes 116/116.
- Phase B/C contract, auth, role, gateway, LINE and regression matrix: PASS.
- Real local nginx upstream-probe matrix: shared production/dev reviewed paths reach the correct
  upstream; unknown API/UI, platform paths, wrong methods, query-reject routes, duplicate/encoded
  path forms and arbitrary RSC paths return 404 without reaching an upstream.
- `line-only`: `/login` and management login API return 404; LINE webhook and development HMR retain
  their existing method/path behavior. The pinned 012 LINE registry digest remains unchanged.
- Shared production: manifest-proven JS/CSS assets pass; unlisted chunks and HMR return 404.
- Frontend Vitest: 91 files / 467 tests PASS; TypeScript typecheck PASS; real Next production build
  PASS (25 pages). The real `.next` manifests compile into exact runtime asset locations.
- Targeted sensitive transport/log/audit regressions: 23 PASS. Ruff and targeted Mypy: PASS.
- Generated fixture and real-build configs: `nginx -t` PASS. Shell syntax checks: PASS.

### Deferred boundaries

- 012 T008 remains `MANUAL ACTION REQUIRED`; this phase did not rotate external credentials, clear
  remote logs/history, inspect ngrok externally, or claim activation readiness.
- At the Phase C checkpoint, Phase D T037–T044 and Phase E T045–T056 were still unchecked; the
  Phase D section below supersedes that historical status.

## Phase D — Remote Session Origin and Rollback

**Date**: 2026-09-05
**Implementation status**: PASS — T037–T044 implemented and locally validated
**Activation status**: Not activation-ready. Phase E and 012 T008 manual incident actions remain
unstarted.
**Repository quality gate**: PASS — full Pytest and Ruff gates pass after resolving the previously
identified Phase A/C verification debt and committed-file format drift.

### Session lifecycle and rollback result

- `session_records` now stores a constrained, indexed `session_origin` plus nullable
  `public_profile`. Migration 0046 backfills existing rows as `legacy`; password login writes
  `local_web` or `remote_management_demo` from trusted request context, while LINE/LIFF session
  creation writes `liff` explicitly. `line_identity_service.py` has no `SessionRecord` creation
  point and therefore required no production change.
- Refresh locks the existing session row, retains the same session/origin/profile, and rejects a
  remote session outside its persisted trusted profile. Remote membership/role loss or profile
  mismatch revokes the session and refresh family; the API commits that security state before
  returning its generic error. Logout uses the same session lock and keeps existing semantics.
- Protected-request context also binds remote sessions to their persisted shared profile. Public
  profile metadata is still accepted only from the configured loopback gateway; origin does not
  grant a role or tenant scope.
- Selective rollback locks all remote-management sessions in stable order, then locks and revokes
  their active refresh records in the same transaction. `local_web`, `liff`, and `legacy` sessions
  are not selected. Aggregate logging contains the fixed `remote_management_rollback` reason and
  counts only, without credential values.
- `rollback_remote_management.py` generates and validates `line-only`, atomically installs and
  reloads the helper-owned nginx config, checks management page/API deny and LINE reachability,
  then invokes database revocation. Failure before those probes prevents revocation. Its JSON
  evidence contains timestamps, duration, route outcomes and aggregate counts only; no public
  tunnel is started. LINE reachability requires the exact expected unsigned-webhook 401 response;
  upstream 500 or an unexpected success cannot be recorded as available and prevents revocation.

### Verification evidence

- Phase D schema/lifecycle/selective-revoke/race/rollback-order plus focused auth, request-context,
  GCE verification and quality-registry suite: 68 PASS. Gateway/profile/nginx regression: 46 PASS.
  LINE/LIFF regression: 22 PASS.
- Full `ruff check .`: PASS. Full `ruff format --check .`: PASS (837 files). Mypy: PASS (25 source
  files). `git diff --check`: PASS.
- Alembic migration validation on local `strayhub_test`: 0045 → 0046 → 0045 → 0046 completed;
  0046 is the single head. Five pre-existing session rows were verified as `legacy`, with zero null
  origins after upgrade.
- Full repository Pytest: 1666 PASS, 2 explained opt-in SKIP. All Phase D PostgreSQL tests passed,
  including selective revocation, refresh-versus-rollback and logout-versus-rollback concurrency.
  The Phase A GCE verification environment now supplies and transports the required synthetic
  `LOGIN_ABUSE_HMAC_SECRET`; the Phase C nginx binary-dependent test is registered in the existing
  explained-skip registry. Seven previously committed Ruff format findings were normalized without
  changing runtime behavior.

### Deferred boundaries

- At the Phase D checkpoint, Phase E T045–T056 remained unchecked. No activation gate, real ngrok
  smoke, external browser journey, external LINE smoke, final sentinel scan, or real five-minute
  rollback drill had been added.
- 012 T008 remains `MANUAL ACTION REQUIRED`; no external credential, history, inspector or log
  action was performed.

## Phase E — Automated Runtime Acceptance and Final Review

**Date**: 2026-09-05
**Automated implementation status**: PASS — T045–T054 and T058–T060 complete
**Feature status**: `READY_FOR_CONTROLLED_ACTIVATION`
**Public activation status**: Not running — T055–T057 complete; drill tunnel stopped after validation

### Controlled runtime acceptance

- A fresh Next production build and isolated loopback gateway (`8002` API, `3002` Next, `8083`
  nginx) exercised the real nginx → Next/FastAPI path against synthetic `strayhub_test` data. It
  did not use a public hostname and is not external activation evidence.
- STAFF completed login, active shelter context, dashboard, animal list, reports, AI review, care
  calendar, refresh, and logout in five repeated core-navigation journeys. A separate expanded
  journey also covered animal detail, timeline, authenticated photo, and report detail. Login was a
  query-free JSON `POST /v1/auth/login`; the browser did not send credentials in a URL.
- SHELTER_ADMIN completed the Core scope five times. Platform/governance/settings/PII surfaces
  remained 404. PLATFORM_ADMIN and VOLUNTEER remote login/API attempts were denied by backend
  policy; existing local/private role semantics were unchanged.
- DB-backed tenant tests deny STAFF and SHELTER_ADMIN access to another shelter's animal, timeline,
  authenticated photo, report, and management resources without resource enumeration. Active
  shelter switching remains server-authorized.
- Production gateway and manifest tests deny arbitrary UI/API/management/platform/docs/debug/
  internal/PII paths, malformed UUIDs, duplicate/encoded/semicolon paths, wrong methods, unknown
  Next internals, HMR, source maps, and image optimization. Approved HTML, RSC/prefetch, and exact
  manifest assets remain available; dev HMR is confined to the dev profile.
- Host validation accepts only the configured normalized authority. Wrong port, userinfo, wildcard,
  path/query/fragment and malformed authorities fail closed; loopback requires the explicit test
  flag. In explicit loopback validation nginx derives trusted client IP from `$remote_addr`; public
  generation continues to consume only edge-overwritten connection metadata.
- The Phase A gateway integration returned 401 for failures 1–4 and 429 for failure 5; the correct
  password remained rejected while locked with `Retry-After: 900`. Forged forwarding/trusted-IP
  headers did not change the gateway-derived identity. Controlled-clock, 20/21 IP-window, expiry,
  unknown-user dummy verification and PostgreSQL concurrency tests all passed.
- Remote login persisted `remote_management_demo` with `shared-demo-production`; refresh retained
  origin/profile. Client-supplied profile/origin data could not override trusted context. Profile
  mismatch and remote requests through the wrong profile remain denied.
- Both `line-only` and shared production LINE matrices passed for webhook, LIFF exchange, QR,
  animal confirmation, photo capability, and care-report routes. `line-only` still denies login and
  all management UI/API routes. The committed 012 LINE registry remains unchanged.
- Runtime photo traversal found and corrected one 013 contract mismatch: FastAPI's authenticated
  animal photo URL carries its existing `v=<checksum>` cache-version query, while the registry had
  rejected every non-empty query. Only `management_animal_photo_api` now preserves that ordinary
  version query; its log policy remains path-only and login/logout query rejection is unchanged.

### Logging, activation gate, and helper evidence

- A random synthetic secret passed through login JSON and a Class B capability request. Raw and
  URL-encoded occurrences were zero in nginx/gateway, Uvicorn/application, generated runtime files,
  test artifacts and audit records. The ordinary-query negative control remained observable, and
  the Class B route still reached FastAPI (invalid synthetic capability returned application 404,
  not a gateway expansion).
- Activation evidence validation requires the exact seven check records, matching normalized
  origin, SHA-256 evidence digests, and explicit `manual_external` classification for public use.
  Synthetic evidence is accepted only behind the test-only flag and cannot satisfy public
  activation. Shared helpers require explicit profile and evidence inputs; default behavior remains
  `line-only`, and validation failure exits non-zero without widening exposure.
- Synthetic demo-data evidence contains only classification, counts, validity, and a digest. The
  fixture seed grants synthetic STAFF the existing medical-care permission required by the Core
  care-calendar journey; no production authorization rule changed.

### Manual T008 / T055 incident evidence

- Authorized operator `JS-LOCAL-01` completed the synthetic demo credential rotation at
  `2026-09-05T07:23:29Z`. The old password returned 401; the rotated password returned 200 through
  query-free JSON `POST /v1/auth/login`.
- Active session and active refresh/session counts were both zero after rotation. Browser local
  history, autofill and Back navigation were reviewed successfully; browser history sync was not
  enabled. The credential owner attested that the exposed value was not reused elsewhere.
- The helper-owned tunnel was stopped and its old endpoint was unreachable. Fixed-string local
  artifact scanning returned no findings, and the static/runtime sensitive-transport checks passed
  with zero raw sentinel occurrences on controllable local surfaces.
- The original ngrok agent/Inspector session was unavailable when checked at
  `2026-09-05T08:01:46Z`; historical request capture and third-party retention are therefore
  `UNVERIFIABLE`, not PASS. This residual risk is recorded without claiming complete third-party
  deletion.
- Full incident evidence is recorded in
  [`runtime-incident-result.md`](../012-sensitive-data-transport-hardening/runtime-incident-result.md).
  The operator-held evidence manifest digest is
  `ec8202b66617c11260d238a9e22665a355ce4f54729f7f25457970ebd790ac79`; it contains no raw
  credential, token, or complete sensitive URL.
- T055 is complete. T056 subsequently supplied the exact reserved-host route/role/tenant/LINE/log
  matrix, and the T057 section below records the completed real external rollback drill.

### Real reserved-host public smoke (T056)

- Authorized operator `JS-LOCAL-01` launched the real reserved HTTPS host with the
  `shared-demo-production` profile, a fresh Next production build, the generated default-deny
  nginx gateway, synthetic `strayhub_test` data, and activation evidence digest
  `0d400f32712034d8636323c8cf7c0c762d33ee3e5d78806002b8aa387cc8a0e0`. The complete hostname
  and all credentials/tokens remain omitted; the normalized host digest is
  `f4c4a3b9b9d377e8`.
- The initial public run exposed a real acceptance defect: ngrok's local HTTP Inspector retained
  request bodies and Authorization headers. A redacted scan counted 21 password-body occurrences
  and 367 Authorization-header occurrences, with zero password query and zero query-bearing
  Referer occurrences. This run was rejected as evidence; its synthetic password was immediately
  rotated and 24 synthetic sessions plus 26 synthetic refresh records were revoked.
- The production helper now passes ngrok `--inspect=false` for
  `shared-demo-production`. A contract test covers this requirement. After a fresh restart and
  credential rotation, the Inspector API remained available for health diagnostics but retained
  zero requests throughout the repeated smoke. Runtime artifact scans found zero raw password,
  Authorization, password-query, or Referer files.
- STAFF and SHELTER_ADMIN each completed five public Core journeys through HTTPS → ngrok → nginx →
  Next/FastAPI: 10/10 passed in 36.8 seconds, with individual journeys between 2.4 and 4.8 seconds.
  Login remained query-free JSON `POST /v1/auth/login`; animal/report detail, authenticated photo,
  refresh, and logout remained successful.
- PLATFORM_ADMIN and VOLUNTEER public login were each denied by the server-side remote role policy.
  The route matrix returned 404 for platform/settings/PII/docs/debug/internal, arbitrary UI/API,
  broad management API, production HMR, unknown Next internals, malformed UUID, wrong-method, and
  login-with-query probes. No broad `/v1/**`, `/v1/management/**`, or `/_next/**` route became
  reachable.
- A real public STAFF session switched active shelter only through the authorized context endpoint.
  Same-tenant identity returned 200; another shelter's animal, timeline, and report each returned
  404 without exposing identifiers or data.
- Public LINE/LIFF entry pages returned 200. An unsigned webhook reached FastAPI and returned the
  expected 401 signature rejection, confirming fail-closed webhook verification without changing
  the committed LINE registry.
- Supporting regression after the public run: helper/gateway/LINE/tenant/log tests `35 passed`;
  TypeScript, Prettier on the public Playwright specs, Ruff on the helper contract test, shell
  syntax, static sensitive-transport policy, production build, nginx syntax, and `git diff --check`
  passed. T056 is complete. This is smoke evidence only and does not satisfy T057's real rollback
  ordering, selective revocation, or five-minute SLA.

### Automated rollback evidence

- The first controlled drill exposed an nginx reload readiness race: management was already denied,
  while the first LINE probe briefly observed the previous Host boundary's 404. The helper failed
  closed and revoked zero sessions. A bounded five-second LINE readiness poll and regression test
  now preserve the original order: reload → management deny → exact LINE 401 → selective revoke.
- The repeated drill switched shared production to `line-only` in `0.141086` seconds. `/login`,
  login API and management API returned 404; unsigned LINE webhook returned the expected 401.
  Two newly created remote STAFF/SHELTER_ADMIN session families were revoked. Five pre-existing
  legacy/local sessions remained active. Existing refresh-vs-rollback and logout-vs-rollback
  PostgreSQL race tests remain green.
- This is automated local timing only. It is not the real external/ngrok five-minute SLA evidence
  required by T057.

### Real external rollback drill (T057)

- Authorized operator `JS-LOCAL-01` restarted the inspection-disabled reserved-host tunnel with
  `shared-demo-production`, synthetic `strayhub_test` data, and the same redacted activation gate
  evidence class used by T056. Before rollback, public STAFF and SHELTER_ADMIN login, authorized
  shelter context switch, and management dashboard each returned 200. Inspector retained zero
  requests.
- The controlled baseline contained two active `remote_management_demo` sessions and two active
  refresh records. Preservation controls contained one active session each for `legacy`,
  `local_web`, and `liff`, plus one active refresh record each for `local_web` and `liff`.
- The first CLI invocation switched and verified the gateway as `line-only`, but reported zero DB
  revocations because the process preferred a separately configured migration URL over the
  explicitly supplied runtime DB URL. This was rejected as incomplete evidence: public management
  was already denied, while both remote sessions remained active. A test-first fix now makes the
  rollback command always revoke from application `DATABASE_URL`; migration credentials cannot
  redirect session cleanup to another database.
- With the runtime DB explicitly selected, the ordered rollback revalidated management deny and
  LINE availability before revoking two remote sessions and two refresh records. From the first
  gateway deny at `2026-09-05T09:08:52.546962Z` to completed revocation at
  `2026-09-05T09:09:30.687514Z` elapsed `38.141` seconds, below the 300-second objective.
- Through the still-running public tunnel after rollback, `/login`, the management home, animals,
  reports, care calendar, login API, and dashboard API all returned 404: management public success
  was 0/7. LINE/LIFF entry pages returned 200 and an unsigned webhook returned the expected 401:
  the bounded LINE availability matrix was 4/4, or 100%.
- Both pre-rollback access tokens and both refresh tokens returned 401. Database verification found
  zero active remote sessions and zero active remote refresh records. The `legacy`, `local_web`,
  and `liff` preservation counts were unchanged. A post-fix runtime probe using only
  `DATABASE_URL` revoked an additional synthetic remote fixture (one session and one refresh),
  proving the migration URL no longer controls the target.
- Runtime artifacts and the ngrok Inspector each retained zero raw password, Authorization,
  password-query, or Referer occurrences. The helper-owned line-only tunnel was stopped after
  evidence collection; this was a bounded drill, not a request for sustained public exposure.
- T057 is complete. T055 incident containment, T056 reserved-host smoke, and T057 external rollback
  now satisfy the feature's controlled-activation prerequisites. A future activation must still use
  the documented explicit profile/evidence gate and normal operator authorization.

### Final quality gates

- Full Pytest after T057: 1707 passed, 2 explained opt-in skips. Phase
  E/auth/session/gateway targeted matrix: 86 passed. Ruff check and Ruff format: PASS (841 files).
  Mypy: PASS (25 source files). Alembic: one head (`0046_remote_session_origin`).
- Frontend Vitest: 91 files / 467 tests PASS. TypeScript typecheck and Prettier check: PASS. Fresh
  Next production build: PASS (25 pages). The new production-gateway STAFF and admin core journeys
  passed five repetitions each; the expanded STAFF run also returned 200 for animal detail,
  timeline, authenticated photo, and report detail. Platform/volunteer deny journeys passed. An exploratory
  broader browser matrix passed 109/112; three existing volunteer-onboarding expectations outside
  this feature still fail against the current volunteer flow and were not modified or used as
  Phase E evidence.
- Shell syntax, touched Python compile, static sensitive-transport checker, production config
  generation, and `nginx -t` for both profiles: PASS. `git diff --check`: PASS at final review.

### Scope and activation boundary

- No MFA, OAuth, SSO, WAF, VPN, Zero Trust, cookie migration, Redis, CDN/CSP redesign, remote
  PLATFORM_ADMIN flow, PII reveal, or broader governance surface was added. T055 incident
  containment, the bounded T056 reserved-host smoke, and the T057 external rollback drill are
  complete. The drill tunnel was stopped; no sustained public activation is running.
- T056 and T057 are complete, and the helper-owned tunnel was stopped after the bounded drill.
  Public activation is not currently running; the feature is ready only for a separately authorized,
  controlled activation through the existing explicit profile and evidence gate.
