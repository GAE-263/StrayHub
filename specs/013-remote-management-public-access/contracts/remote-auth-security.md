# Contract：Remote Authentication Security

## Request contract

正常登入保持：

```http
POST /v1/auth/login
Content-Type: application/json

{"username":"...","password":"..."}
```

- Credential 不得進 query、path、fragment、referer 或 access log。
- `/login?username=...&password=...` 仍由 Phase A 的 replace canonicalization 清為 `/login`；本功能
  不改回 GET login。
- Gateway 對 login API 的 non-empty query 直接拒絕。

## Account identity and enumeration resistance

Account rate-limit key 的唯一 normalization：

```text
NFKC(input) -> trim Unicode surrounding whitespace -> casefold
```

normalized value 只用於 HMAC abuse subject，不改變既有 authentication identity matching 規則，
也不回傳、不記 raw log。未知、disabled、無 password hash、角色不符或無有效 membership 均使用
generic authentication failure。未知／不可登入帳號執行 dummy Argon2 verification，避免明顯
timing shortcut。

## Account lock contract

| 狀態 | 結果 |
|---|---|
| 第 1–4 次連續錯誤 | 401 generic invalid credentials |
| 第 5 次錯誤 | 原子設定 15 分鐘鎖定，該次立即 429 |
| 鎖定期間任何 password | 429，不做成功登入 |
| 鎖定到期 | 下一次嘗試由 0 次開始 |
| 未鎖定且登入成功 | 建立 session，清除 account failure state |

429 必須有整數秒 `Retry-After`，值最少 1；body 不說明帳號是否存在，也不顯示目前 failure
count。並行 request 對同一 normalized subject 必須序列化，使只有前四次能得到 401，第五次及其後
得到 429。

## Trusted-source IP contract

- Window：rolling 15 minutes。
- Capacity：每個 trusted source 最多 20 個被接受進 evaluation 的 login requests。
- 第 21 次：429 + `Retry-After`，不新增事件。
- 成功與失敗都計入；成功不清空 window。
- API 只使用 edge remove/overwrite 後的 `X-StrayHub-Trusted-Client-IP`；不得使用 request body、
  arbitrary `X-Forwarded-For` 或 client-provided同名 header。
- IPv4/IPv6 必須先由標準 parser canonicalize；invalid/multiple value fail closed。

若 account lock 與 IP limit 同時成立，回相同 generic 429；`Retry-After` 取讓 request 最早可重新被
評估的安全值，不透露是哪一種 limiter。

## Atomicity and failure behavior

- 所有 limiter 讀改寫都在 PostgreSQL transaction，並以 digest-keyed advisory lock 序列化。
- Database timeout/unavailable 時 login 回 generic 503；不得 fail open、不得建立 session。
- Clock 使用 UTC server clock；測試用 dependency-injected clock，不用 sleep。
- HMAC key 缺漏、placeholder 或過短時，shared-demo profile 啟動失敗。

## Public-role contract

- Password 正確後，公開 profile 還須確認至少一筆目前有效且 role 為 `STAFF` 或
  `SHELTER_ADMIN` 的 membership，才可建立 remote session。
- `PLATFORM_ADMIN` 不因知道正確密碼而取得 public management session。
- Refresh 使用 session 上的 server-derived origin/profile；不得由 caller 把 legacy/local session
  改標為 remote，也不得藉 refresh 繞過角色與 membership 檢查。
- Public-role denial 不改變 private/local login contract。

## Session and rollback contract

公開登入成功建立：

```text
session_origin = remote_management_demo
public_profile = shared-demo-production | shared-demo-dev
```

Rollback 順序不可顛倒：

1. 切換 gateway 為 line-only（或等價 deny management），reload 並以 public host 驗證 management
   page/API 已不可達、LINE flow 仍可達。
2. DB transaction 撤銷所有 active remote-management session 與其 refresh token family。
3. 驗證舊 access token、refresh token 均失敗，保存起訖 timestamp、route probe 與 revoke count。

兩階段總時間不得超過 300 秒。rollback command 不得輸出 token、username、raw IP 或 password。

## Logging/audit contract

允許的 security event 欄位：event code、request ID、UTC time、digest prefix、profile、HTTP outcome。
禁止：raw username、password、Authorization、access/refresh token、raw trusted IP、完整 request URI、
referer。若寫入 audit before/after JSON，仍須經 012 defense-in-depth redaction。

## Deterministic tests

- NFKC/casefold/trim 等價輸入共用 account state。
- 第 4/5 次與 15 分鐘邊界。
- 20/21 次與 oldest-event `Retry-After`。
- 兩個 repository/service instance 共享狀態。
- 並行第五次與並行第二十一次。
- spoofed/multiple/invalid IP header fail closed。
- unknown account 執行 dummy verifier 且 response 與 known invalid 相同。
- platform/volunteer/expired membership denied；staff/admin allowed。
- remote session refresh 與 rollback revocation。
- sentinel credential/token 不出現在 nginx、application、audit、script output。
