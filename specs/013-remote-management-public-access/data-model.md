# Data Model：Remote Management Public Access

## 設計範圍

本功能不新增或複製任何 shelter-owned CRM 業務資料。新增資料只服務 authentication abuse
control 與 remote-session rollback；所有欄位均由伺服器產生，client 不得指定。

## 1. `login_account_abuse_states`

每個 normalized account subject 最多一列，作為跨 API worker 的連續失敗與鎖定狀態。

| 欄位 | 型別／限制 | 說明 |
|---|---|---|
| `id` | UUID PK | 既有 identity mixin 慣例。 |
| `subject_digest` | String(64), unique, non-null | `HMAC-SHA256(key, "account:" + normalized_username)`；不保存 raw username。 |
| `consecutive_failures` | Integer, non-null, default 0, check 0–5 | 尚未成功登入前的連續錯誤次數；5 代表已觸發鎖定。 |
| `locked_until` | timestamptz, nullable | 第 5 次錯誤當下設為 `now + 15 minutes`。 |
| `last_failed_at` | timestamptz, nullable | 最近一次計入的密碼失敗時間。 |
| `created_at` / `updated_at` | timestamptz | 既有 audit timestamp。 |

### Key 與鎖定

- username normalization 固定為 Unicode NFKC → trim → casefold；前後順序不得由 caller 改變。
- transaction 先依 `subject_digest` 取得 PostgreSQL transaction advisory lock，再讀取／upsert row，
  以涵蓋「row 尚不存在」的並行情境。
- advisory lock key 由 digest 的固定 64-bit projection 產生；collision 只會造成額外序列化，不會
  合併資料列或授權。
- 正確密碼只有在 state 未鎖定時才可成功，成功後刪除該 state row。
- 鎖定到期後下一次密碼驗證從 0 次重新開始；可刪除過期 row 後重新計數。

### State transition

```text
ABSENT/0
  -- wrong --> 1 -- wrong --> 2 -- wrong --> 3 -- wrong --> 4
  -- fifth wrong --> 5 + locked_until (HTTP 429)
  -- during lock, any password --> unchanged (HTTP 429)
  -- lock expires --> 0
  -- correct while unlocked --> row deleted + session issued
```

第 1–4 次錯誤回相同 generic 401；第 5 次與鎖定期間回相同 generic 429 + `Retry-After`，不得由
response 區分帳號存在、狀態或角色。

## 2. `login_ip_attempts`

每個已接受進入 login evaluation 的來源嘗試一列，精確支援 rolling 15-minute window。

| 欄位 | 型別／限制 | 說明 |
|---|---|---|
| `id` | UUID PK | 唯一事件。 |
| `source_digest` | String(64), non-null, indexed | `HMAC-SHA256(key, "ip:" + canonical_ip)`；不保存 raw IP。 |
| `attempted_at` | timestamptz, non-null, indexed | server clock；不可由 request 提供。 |

複合索引：`(source_digest, attempted_at)`。

### Rolling-window transaction

1. 以 `source_digest` 取得 transaction advisory lock。
2. 刪除該 source 中 `attempted_at <= now - 15 minutes` 的 row。
3. 依時間排序讀取 window 內事件；若已有 20 筆，不新增第 21 筆，回 429。
4. `Retry-After = ceil(oldest_counted.attempted_at + 15m - now)`，最少 1 秒。
5. 少於 20 筆時插入本次事件，再進行 account/password 流程。

IP 配額包含成功、失敗、未知帳號與被 account lock 拒絕的 login request；被 IP gate 擋下的第
21 次不再新增事件，避免惡意流量延長自身 window。成功登入不清除 IP window。

### 保存與清理

- 判定所需資料只保留 15 分鐘；每次該 source 的操作做同步 pruning。
- 另提供 bounded opportunistic cleanup，刪除所有已超出 window 的 row；不需新排程服務。
- 資料不得進一般 audit before/after payload；安全事件只能記 digest prefix、結果代碼與 request ID。

## 3. `session_records` 擴充

| 新欄位 | 型別／限制 | 說明 |
|---|---|---|
| `session_origin` | String(40), non-null, indexed | `legacy`、`local_web`、`liff`、`remote_management_demo`。 |
| `public_profile` | String(40), nullable | remote session 為 `shared-demo-production` 或 `shared-demo-dev`；其他 origin 必須為 null。 |

### Migration

- Schema migration 對既有 row 以 server default `legacy` backfill，再設 non-null。
- 新的 password login 與 LIFF exchange 呼叫端必須明確傳入 server-derived origin；不得取自 JSON
  body、query 或未驗證 header。
- check constraint：`session_origin = 'remote_management_demo'` 時 `public_profile` 必須是兩個命名
  profile 之一；其他 origin 的 `public_profile` 必須為 null。
- 索引 `(session_origin, status)` 支援緊急撤銷。

### Lifecycle

- Refresh token rotation 不建立新 session，沿用原 session 的 origin/profile。
- remote profile 下 refresh 仍需重新驗證 user active、有效 shelter membership 與角色為
  `STAFF`/`SHELTER_ADMIN`；不符合即撤銷 session/family 並回 generic 401/403。
- Rollback 將所有 `session_origin='remote_management_demo' AND status='active'` 設為 revoked，並
  在同一 DB transaction 撤銷相連 refresh token records。
- Access token 每次 protected request 仍查 server-side session，故 session revoke 立即生效，不必
  等 access-token TTL。

## 4. Runtime-only value（不持久化）

### `ExposureContext`

| 欄位 | 值 | 信任來源 |
|---|---|---|
| `profile` | none / shared-demo-production / shared-demo-dev | nginx 固定覆寫，且 request 必須來自 configured loopback gateway。 |
| `client_ip` | canonical IPv4/IPv6 | ngrok `conn.client_ip` 經 remove/overwrite 後傳入。 |
| `request_id` | 既有 correlation ID | gateway 產生或保留既有可信格式。 |

如果可信 metadata 缺漏、重複、格式錯誤或 profile 未知，公開 launcher health check 失敗；API 不得
回退去信任 client 的 forwarding header。

`GET /v1/auth/me` response 可加入 nullable `public_exposure_profile`，其值只來自當次 request 的
`ExposureContext.profile`。Frontend 用它隱藏 out-of-scope navigation、report correction/archive 與
care reminder mutation controls；它不是 token claim、不是 client-selectable role，也不能取代 route/API
authorization。

## 5. 資料隔離與權限

- 兩個 abuse-control table 是 platform authentication metadata，不屬於任何 shelter，也不包含
  shelter business ID；只可由 authentication repository 存取。
- `session_records.active_organization_id` 與既有 membership/RLS 規則不變。
- `session_origin` 不授予角色、organization 或 route 權限；它只縮限公開 request 及支援撤銷。
- 任一公開 API 仍須以 access token 對應的 server session 與 active organization 決定 scope，
  client 傳入的 organization/resource ID 不得擴大資料範圍。

## 6. 失敗與復原

- PostgreSQL unavailable：login fail closed（503），不得略過 account/IP gate；既有已登入 request
  依既有 session DB failure behavior 處理。
- HMAC secret 缺漏／placeholder：shared-demo launcher/API 啟動失敗；line-only/local 不因未啟用
  profile 被迫公開。
- Migration rollback：先切回 line-only 並撤銷 remote sessions，再 downgrade schema；不得先移除
  session origin 而失去撤銷目標。
- Clock 必須使用 server UTC；測試注入 clock，不修改 production system time。
