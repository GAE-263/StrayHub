# Data Model: 敏感資料傳輸與紀錄防護

本功能不新增 CRM 持久化 entity。以下是安全政策、runtime request 與驗證 evidence 的概念模型；實作可採靜態 registry／contract fixtures，不需 migration。

## 1. SensitiveDataClass

| Field | Type | Rules |
|---|---|---|
| `code` | enum | `forbidden_url_secret`（Class A）、`restricted_url_capability`（Class B）、`public_identifier`（Class C）、`ordinary_query`（Class D） |
| `examples` | list | 僅列參數名稱或 synthetic value，不存真實秘密 |
| `allowed_locations` | set | URL、header、request body、response body、terminal；預設 deny |
| `log_policy` | enum | `omit_query`、`redact_value`、`allow` |
| `incident_action` | enum | rotate、revoke、expire、review、none |

### Validation

- `forbidden_url_secret` 不得允許 URL／fragment／QR／redirect destination。
- `restricted_url_capability` 必須對應 `UrlException`；workflow locator 是此類的 purpose 子型別，不另放寬政策。
- `public_identifier` 不得單獨構成授權，server 仍須驗證租戶與角色。
- `ordinary_query` 不得包含 credential 或可直接授權的資訊。

## 2. UrlException

| Field | Type | Rules |
|---|---|---|
| `key` | string | query／callback key，例如 `token`、`qr_token`、`entry` |
| `route_pattern` | string | 限定 consumer route，不接受全域 wildcard |
| `classification` | enum | restricted URL capability；public identifier 不需安全例外，但需登錄用途 |
| `purpose` | string | 單一明確用途 |
| `issuer` / `consumer` | string | 既有模組或外部平台 |
| `max_lifetime_seconds` | integer/null | capability 必填；穩定 locator 若無 TTL，必須可撤銷且說明理由 |
| `organization_bound` | boolean | shelter-owned capability 必須為 true |
| `resource_binding` | string | animal、media、entry target、callback session 等 |
| `replay_policy` | enum | single-use、bounded-reuse、revocable |
| `scrub_event` | string | 何時從可見 URL 移除 |
| `log_policy` | enum | omit query 或 redact value |
| `owner` | string | 維護模組／團隊 |
| `tests` | list | contract、security、isolation、runtime evidence |

### Initial registry candidates

| Key / value | Class | Current purpose | Required disposition |
|---|---|---|---|
| `password` | Class A | login | 移出 URL；legacy request 不採信 |
| `access_token`, `refresh_token`, `id_token` | Class A | session／LINE identity | body/header only；callback legacy scrub |
| public photo `token` | Class B | LINE/adoption image fetch | retain 300s policy, tenant/resource/purpose binding, query-free logs |
| `qr_token` | Class B | resolve animal QR | no fixed TTL; verify tenant/resource/revocation; scrub after capture; no raw logs |
| `entry` | Class B | select shelter/application target | 90-day opaque reference、server-validated、revocable、log-redacted; preserve only through required LIFF recovery |
| signed storage URL | Class B | authorized staff download | response only, 300s current lifetime, never application-log full URL |
| `organization_id`、resource UUID | Class C | public target/resource identifier | never trust as authorization; preserve server-side tenant checks |
| `v` checksum | Class D | browser cache version | non-authoritative; may retain standard diagnostics |
| search/page/date/status | Class D | management filtering | retain existing behavior |

## 3. ExposureSurface

| Surface | Can see URL before app? | Control |
|---|---:|---|
| Browser address/history/bookmark | yes | source prevention + canonicalization |
| Password manager/autofill | form fields | no password prefill; correct autocomplete semantics |
| ngrok／external tunnel | yes | route allowlist; source prevention; short retention where configurable |
| nginx | yes | sensitive-route log format without query/Referer |
| Next runtime/proxy | yes | no secret URL creation; sanitized diagnostics; forwarding policy |
| Uvicorn access | API requests | sensitive filter + tests |
| Application logger | payload/context/errors | handler/filter + structured safe fields |
| Audit log | business events | no raw credential; only type/result/fingerprint |
| CLI/terminal | explicit issuance | terminal-only warning; no accidental file/log persistence |
| Test artifact/HAR/screenshot | runtime evidence | synthetic sentinel; artifact scan and cleanup |

## 4. DemoExposureMode

### States

```text
local_only
  → public_line_liff (default explicit tunnel start)
  → remote_management_demo (separate explicit opt-in)
  → stopped
```

### Rules

- `local_only`: management routes and static synthetic credentials may be documented locally.
- `public_line_liff`: allowlist only; management login/API denied; no fixed password printed to public-run output.
- `remote_management_demo`: synthetic-only guard, ephemeral credential, start/end warning, expiry/revocation evidence.
- `stopped`: helper-owned process stopped, temporary config/log removed, ephemeral credential invalidated.

## 5. SecurityRegressionEvidence

| Field | Description |
|---|---|
| `run_id` | 不含秘密的唯一執行識別 |
| `scenario` | login／LIFF／QR／photo／download／error／cross-tenant |
| `sentinel_digest` | sentinel 的不可逆摘要；報告不回寫原值 |
| `surfaces_checked` | 本次實際掃描邊界 |
| `result` | PASS／FAIL／BLOCKED |
| `findings` | 路徑與類型，不含原值 |
| `cleanup_status` | temporary artifact 與 tunnel 是否清理 |

## State transitions for URL data

```text
created
  → classified
    → Class A forbidden → rejected / moved-to-body-or-header
    → exception-required → registered → issued → consumed
       → scrubbed-from-visible-url
       → expired / revoked
    → Class C public identifier → server-authorized before resource access
    → Class D ordinary-query → retained
```

任何 `unclassified` 敏感候選不得進入 release。
