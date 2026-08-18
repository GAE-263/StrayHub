# 快速開始：志工報名與限時授權驗證

本指南用於實作後驗證 [spec.md](spec.md)、[data-model.md](data-model.md) 與 [contracts](contracts/README.md)。P0 使用虛構 local LINE identity／Messaging adapter、兩個收容所與 deterministic entry reference；不需 production LINE credential，也不依賴 004 的 route implementation 或 P1 招募活動／排班／提醒。

## 前置條件

- Docker Desktop／Docker Compose
- Python 3.11+ 與 `uv`
- Node.js、npm
- 已依 `.env.example` 建立 local-only `.env` 與 JWT keys
- local LINE verifier 能把測試 id token 映射到虛構 LINE user id
- 所有測試資料均為虛構個資，不使用正式志工資料或 LINE credential

## 預期 local fixtures

| Fixture | Organization | 初始狀態 | 用途 |
| --- | --- | --- | --- |
| `Ulocal-applicant-new` | ORG-A | 無 User／Binding／Application | 首次報名原子建立身分 |
| `Ulocal-applicant-pending-a` | ORG-A | pending | duplicate submit、withdraw、batch approve |
| 同一 LINE user | ORG-A + ORG-B | 各自 pending | 跨 organization 獨立決策 |
| `Ulocal-applicant-rejected` | ORG-A | rejected | reapply 與歷史保留 |
| `local-volunteer-a` | ORG-A | active，168 小時內 | effective access regression |
| `local-volunteer-expired-a` | ORG-A | expired + preserved draft | request deny、reapply、資料保存 |
| `local-volunteer-revoked-a` | ORG-A | revoked | session/context cleanup |
| `local-volunteer-future-a` | ORG-A | valid_from 在未來 | upcoming，不可提早使用 |
| `local-shelter-admin-a` | ORG-A | SHELTER_ADMIN | 正常管理員操作 |
| `local-staff-a` | ORG-A | STAFF | 管理 endpoint 拒絕 |
| `local-platform-admin` | 明確 target ORG-A/B | PLATFORM_ADMIN | 受控跨機構支援與 Audit |

ORG-A policy fixture 將預設期限改為 72 小時，ORG-B 保持新 organization 建立 transaction 內取得的初始 168 小時；另準備一個 `applications_enabled=false` 且已有 pending applicant 的 ORG-C。三者各有 active opaque entry reference，資料庫只保存 digest。另準備 100 筆人工流程 fixture、至少 1,200 筆 ORG-A all-filtered fixture、10 筆 ORG-B 對照資料、停用 user/org 的未清理 Session/context，以及涵蓋所有通知事件的 failed delivery。display name 包含長中文、重複名稱與不同 Unicode，確保 UI 不把名稱當唯一識別。

## 建置資料庫

啟動 PostgreSQL／MinIO：

```bash
docker compose -f infra/local/docker-compose.yml up -d postgres minio
```

驗證 Alembic 單一 head 並升級：

```bash
uv run alembic heads
uv run alembic upgrade head
uv run alembic current
```

載入虛構資料：

```bash
uv run python -m scripts.seed_local
```

正式環境樣式的 entry reference 發行／輪替以受控 script 執行；raw token 只在 stdout／secret handoff 顯示一次，測試不得把輸出提交進 Git：

```bash
uv run python scripts/issue_volunteer_entry_reference.py --organization-code ORG-A --rotate
```

### Migration 驗證

對空資料庫可直接 upgrade head；對含 005 前既有 VOLUNTEER 的 production-like 資料庫另驗證 staged rollout：

```bash
uv run alembic upgrade 0024_volunteer_access_expand
uv run python scripts/configure_volunteer_access_policy.py --organization-code ORG-A --duration-hours 72
uv run alembic upgrade head
```

- 空資料庫可直升 head。
- migration 後新建 organization 與初始 policy 在同一 transaction 成功，預設 `applications_enabled=true`、期限 168 小時；注入 policy insert failure 時 organization 也不落庫。
- 只有既有 active、unbounded VOLUNTEER 產生 `legacy_migration` application/grant。
- `valid_from` 是同一 migration timestamp；ORG-A 依 staged policy 得到 72 小時，未設定的 ORG-B 得到 168 小時，Grant 均快照 policy version/duration。
- active VOLUNTEER 的 null／無效 expiry 數為 0。
- disabled／revoked／expired 或其他非有效 Membership 保持原狀，不被自動啟用，且不建立 synthetic Application／Grant。
- migration Audit actor 可辨識為 `SYSTEM_MIGRATION`，不冒充管理員。
- policy 更新只影響更新後新建 decision；既有 Application／Batch／Grant／Membership 時間不被追溯改寫。
- raw entry reference 不出現在資料庫、log 或 Audit；rotation 可先發新 reference，再撤銷舊 reference。

production-like migration 測試不得以 downgrade 刪除已建立的正式歷史；回復演練採前向 migration。

## 啟動本機服務

分別啟動 API、Web 與 Worker：

```bash
uv run python -m uvicorn services.api.app.main:app --reload --host 127.0.0.1 --port 8001
npm --prefix apps/web run dev -- --hostname 127.0.0.1 --port 3001
uv run python services/worker/worker.py
```

入口：

- Web：<http://127.0.0.1:3001>
- 志工報名：`http://127.0.0.1:3001/volunteer-application?entry=<local-reference>`
- 管理申請：<http://127.0.0.1:3001/volunteers/applications>
- 授權管理：<http://127.0.0.1:3001/volunteers/access>
- 通知失敗：<http://127.0.0.1:3001/volunteers/notifications>
- 志工授權設定：<http://127.0.0.1:3001/settings/volunteer-access>
- API health：<http://127.0.0.1:8001/healthz>

## Contract 與靜態品質

先驗證規劃 contract 可解析，實作時再驗證 canonical merge 與 generated types：

```bash
uv run python -c "import yaml; yaml.safe_load(open('specs/005-volunteer-access-approval/contracts/volunteer-access.openapi.yaml'))"
npm --prefix packages/contracts run generate
npm --prefix packages/contracts run check
uv run ruff check .
uv run ruff format --check .
npm --prefix apps/web run typecheck
npm --prefix apps/web run format:check
```

預期：

- additive paths 已合併 canonical OpenAPI。
- Membership generated type 有 nullable validity fields 與 access version。
- all-filtered selection、Batch progress/item cursor、Grant mutation、own-status、notification failure list 與 bulk retry types 可由 Web 直接使用。
- generated file 無 drift，不以手改 generated TypeScript 通過檢查。

## 自動化測試順序

### 1. Domain 與 service unit tests

```bash
uv run pytest tests/unit/test_volunteer_access_time.py tests/unit/test_volunteer_access_decisions.py -q
```

至少涵蓋：

- `[valid_from, expires_at)` 邊界、UTC、新 organization 初始 168 小時，以及 ORG-A 自訂 72 小時 policy。
- policy version/duration snapshot；policy 更新不追溯既有 Batch／Grant。
- `expires_at <= valid_from` 拒絕。
- upcoming／active／expired／revoked effective status。
- pending application 合法／非法 transition。
- approve 永遠只產生 VOLUNTEER。
- reject/revoke 空白 reason 拒絕。
- 縮短至 now/過去需要 `confirm_immediate_expiry`。
- operation fingerprint、expected version、duplicate idempotency。
- all-filtered target snapshot、500-item chunk claim、stale claim recovery 與 terminal item 不重做。

### 2. API contract 與 persistence integration

```bash
uv run pytest \
  tests/contract/test_volunteer_access_contract.py \
  tests/integration/test_volunteer_access_application.py \
  tests/integration/test_volunteer_access_batch.py \
  tests/integration/test_volunteer_access_expiration.py \
  tests/integration/test_volunteer_access_notifications.py -q
```

預期：

- 首次 apply 原子建立一個 User + Binding + pending Application，Membership 為 0。
- 未知 LINE identity 只呼叫 status 時，User、Binding、Membership、SessionRecord 與 WebhookSession 新增數均為 0。
- `applications_enabled=false` 阻止新 apply，但既有 applicant 仍可取得自己的安全 status；兩者都不載入 protected data。
- 同 LINE user/org 重送只回同一 pending；跨 organization 各自有一筆。
- status/withdraw 只能操作自己；terminal application 不可修改。
- approve 建立／啟用唯一 Membership + 新 Grant；未覆寫時使用 decision 當下 organization policy 並快照 version/duration。
- reject 不建立 Membership。
- reapply/regrant 新增週期且舊資料不變。
- notification failure 不回滾 domain transaction；統一失敗清單包含所有 event type，單筆／多筆 retry 不重放 decision。

### 3. 批次 100 筆人工流程、1,200 筆全選與並行衝突

```bash
uv run pytest tests/performance/test_volunteer_access_batch.py -q
```

測試矩陣：

1. ORG-A 管理員載入 100 筆 pending，選取目前 filter 全部。
2. common default 使用 ORG-A policy 的 72 小時，10 筆 individual override，其中含 future start 與較長期限。
3. 提交前由第二位管理員先處理 3 筆，另撤回 2 筆。
4. 第一批送出並取得 95 succeeded + 5 conflict（依 fixture 固定）。
5. 重送相同 operation id／payload，結果完全相同且 Membership/Grant/Audit 不增加。
6. 同 operation id 改 payload 收到 409，domain mutation 為 0。
7. 只把 5 個 failed/conflict target 以新 operation id 重試。
8. 以 1,200 筆 ORG-A pending 執行 `all_filtered`；確認 Batch requested_count=1,200、item snapshot=1,200，並至少經過 3 個不超過 500 筆的 claim chunk。
9. snapshot commit 後新增 5 筆 pending，確認不進入既有 Batch；中斷第二個 chunk 後恢復，已成功項目不重做、未處理 target 不遺失。

驗收：

- 成功項目不因其他衝突回滾。
- 每項 Audit 共用 batch operation id，batch counts 可對帳。
- 100 筆從選取到結果在 5 分鐘人工流程內完成；API performance 測試另記錄 p95，但不以不穩定 wall-clock assertion 取代一致性 assertion。
- 1,200 筆 snapshot 與逐筆結果完整率為 100%；確認後新增誤納入、chunk retry 重做成功項目與遺失 pending item 均為 0。
- ORG-B 10 筆資料、count、result、Audit 全部不可見且不變。

### 4. Request-time invalidation 與 Worker 收斂

使用可注入 clock 或短期 fixture，不以長時間 sleep 驗證：

```bash
uv run pytest tests/integration/test_volunteer_access_expiration.py tests/security/test_request_context.py -q
```

預期：

- 在 expires_at 前一個最小時間單位可通過；expires_at 精確時刻立即拒絕。
- Worker 尚未執行時，protected API 仍立即拒絕。
- Worker tick 後 60 秒 SLA 內 Membership/Grant 為 expired、Audit/outbox 存在。
- target organization 的 Session context 清空、Webhook Session expired。
- organization 或 user 停用後 request-time 立即拒絕；即使沒有後續 request，Worker tick 後 60 秒內 target Session/context 仍清空。
- 同 user 在另一 organization 的有效 Membership 不受影響。
- draft/report/media row count 與原始內容不變；重新授權後仍依既有 owner/context 規則可恢復。
- 重跑 Worker 不產生第二筆 expiry Audit 或 notification。

### 5. Security 與 tenant isolation

```bash
uv run pytest \
  tests/security/test_volunteer_access_authorization.py \
  tests/isolation/test_volunteer_access_isolation.py \
  tests/isolation/test_full_cross_tenant_matrix.py -q
```

至少驗證：

- STAFF／VOLUNTEER 無法讀取 application list/count、batch、Grant、notification。
- ORG-A SHELTER_ADMIN 提交 ORG-B application/grant UUID 時，回應不透露存在性且 DB 不變。
- PLATFORM_ADMIN 對 list/detail/mutation 每次都明確指定 organization 並提供 `X-Platform-Support-Reason`；缺少 target/reason 的成功率為 0，合法 read/write 的 platform actor/reason Audit 覆蓋率為 100%。
- platform-support Audit 必須在第一個 management endpoint 啟用前即涵蓋 success、denied、not-found、validation failure 與 exception result。
- PLATFORM_ADMIN 不得取得跨 organization 混合 application/grant/notification list。
- raw/tampered/cross-purpose entry reference 不建立 application；有效 reference 也不自動核准。
- pre-context runtime 無法直接 SELECT entry reference table；只能由 resolver 以 digest/purpose 取得 active reference id 與單一候選 organization。
- pending/rejected/withdrawn/future/expired/revoked protected request 成功率為 0。
- RLS 在漏寫 ORM tenant filter 的專門測試中仍阻止跨 tenant row。
- error/log/audit 不含 id token、LINE user id、channel credential 或其他志工資料。

### 6. Frontend unit 與 browser flow

```bash
npm --prefix apps/web run test
npm --prefix apps/web exec -- playwright test e2e/volunteer-access-approval.spec.ts
```

Playwright 至少涵蓋：

- 首次 LINE onboarding：顯示正確收容所 → 確認 → pending，不出現帳密欄位。
- pending reload 顯示原狀態；double click/network retry 不重複申請。
- pending 頁沒有動物、草稿、回報或管理 request。
- rejected/withdrawn/expired 可重新申請，舊週期仍可在管理 Audit 對帳。
- 管理員以 filter 全選、部分選取、整批期限、個別 override、確認 dialog 完成批次。
- `/settings/volunteer-access` 可調整 organization 預設期限；新核准使用新值，既有 Batch／Grant 不變。
- 超過 500 筆仍顯示完整 snapshot count、同一 logical batch 進度與 cursor 分頁逐筆結果，不把全選降級為目前頁面。
- partial result 逐項顯示 succeeded/conflict/failed，retry 只包含失敗 target。
- Grant 延長、縮短、立即失效確認與 revoke reason。
- `/volunteers/notifications` 統一顯示各事件 failed/retry_wait，可依事件／時間篩選；只有 failed 可選取並執行單筆或多筆重試，retry_wait 顯示等待背景重試且不可重複排入；Grant/Application 正式狀態仍正確。
- STAFF／VOLUNTEER deep link 不掛載管理名單或發出 list request。

### 7. Responsive、keyboard、axe 與 visual

```bash
npm --prefix apps/web run test:a11y:browser
npm --prefix apps/web run test:axe
npm --prefix apps/web run test:visual
```

P0 至少驗證 360x800、768x1024、1024x768、1440x900。Visual baseline 只有在 reviewer 確認預期 UI 後更新：

```bash
npm --prefix apps/web run test:visual:update
```

驗收：

- checkbox、filter、select-all、per-item time override、confirm、result summary 可全鍵盤操作。
- dialog 有 focus trap／return focus；批次結果用 live region 或等效可理解提示。
- status、conflict、notification failure 不只靠顏色表達。
- 長中文姓名、時區後完整日期、100 筆 table 在 360px 不遮住主要操作；必要時使用水平 table scroll 或 row detail，不截斷關鍵期限。
- Axe critical／serious violations 為 0。

## 手動驗收流程

### 1. 首次報名與無權限狀態

1. 從 ORG-A local entry 開啟 `/volunteer-application`。
2. 確認畫面顯示 ORG-A 名稱，沒有動物數量、狗狗資料或帳密表單。
3. 送出後確認 pending 與 submitted time；DB 只有一個 User、Binding、Application，Membership 為 0。
4. reload、返回、重送，確認仍是同一 application id/version。
5. 直接開啟 `/animal-confirmation` 或呼叫 `/v1/animals`，確認無 protected data。
6. 以同 LINE identity 開 ORG-B entry，確認可建立獨立 ORG-B pending，但看不到 ORG-A 狀態。
7. 以未知 LINE identity 只查 status，確認沒有建立 User/Binding；再開啟 ORG-C 停用入口，確認新 apply 被阻止但既有 pending applicant 仍可看 own status。

### 2. 管理員批次核准／拒絕

1. 以 `local-shelter-admin-a` 登入 `/volunteers/applications`。
2. 先在 `/settings/volunteer-access` 確認 ORG-A 預設為 72 小時；另建立新 ORG-B，驗證 organization 與初始 168 小時 policy 同 transaction 出現。修改設定後確認 before/after Audit，既有 Grant 不變。
3. 篩選 pending，確認只看 ORG-A；使用目前 filter 全選。
4. 核准 dialog 預填「從核准時起 72 小時」，調整整批與個別期限。
5. 確認摘要後提交，檢查逐項結果與到期時間；之後改 policy，不得改動這批既有 Grant。
6. 對另一批輸入拒絕原因；拿掉原因時送出應被阻止。
7. 以第二個管理 Session 製造 stale version，確認第一畫面顯示 conflict 且較新決策未被覆寫。
8. 使用 `local-staff-a` 與 ORG-B admin 開相同 deep link，確認不顯示名單、count 或 request result。

### 3. 授權有效期、調整與撤銷

1. 核准一筆 ORG-A default grant，確認 `expires_at - valid_from = 72 hours`；ORG-B 未調整 policy 時為 168 小時。
2. 在開始前確認 status upcoming，protected request 被拒。
3. 時間進入有效區間後確認 request 可通過且顯示收容所與到期時間。
4. 延長／縮短期限，確認下一個 request 立即使用新值。
5. 嘗試縮短到過去但不確認，應 422 且 UI 保留輸入；確認後立即 expired 並清除 ORG-A context。
6. 另核准一筆後以 reason 撤銷，確認 ORG-A request 拒絕、ORG-B access 不受影響。
7. 確認草稿與回報未刪除；新 application 核准後建立新 Grant id，舊 Grant 仍 expired/revoked。
8. 停用 user 或 organization 後不再發出 request，等待一次 Worker tick，確認 60 秒內 target Session/context 清除，另一 organization context 不受影響。

### 4. 通知 failure

1. 將 local Messaging adapter 設為報名送出、核准、拒絕、期限變更、到期與撤銷各一次 transient/terminal failure。
2. 執行來源 action，確認 Application/Membership/Grant/Audit 都已 commit，沒有因通知失敗回滾。
3. 開啟 `/volunteers/notifications`，確認所有事件都出現在 ORG-A 統一清單，ORG-B 項目不可見；依事件與時間篩選。
4. 恢復 adapter 後，以一個 `operation_id` 選取多筆 manual retry；重送相同 payload 回既有結果，不同 payload 回 409。
5. 確認 retry 只改 notification/retry batch/attempt，Membership/Grant/Application count 與版本不增加。
6. 模擬 user 封鎖 LINE 的 terminal failure，確認項目仍保留安全摘要，且志工仍可由 own-status page 取得正式結果。

### 5. PLATFORM_ADMIN 支援稽核

1. 以 `local-platform-admin` 呼叫 ORG-A application、grant、notification list；不帶 `X-Platform-Support-Reason` 時全部拒絕且不執行 business query。
2. 帶「協助 ORG-A 排查志工通知」後只取得 ORG-A 資料；每次 read 都有 target organization、actor、reason 與 result Audit。
3. 對 ORG-A policy 或 Grant mutation 使用另一明確原因，確認 mutation Audit 與 platform-support Audit 都可對帳。
4. 嘗試省略 organization path 或要求 ORG-A/ORG-B 混合 list，確認 contract 不提供且成功率為 0。

### 6. 004 整合預備驗收

在 004 尚未實作時，以 service/contract test 證明：

- effective Membership helper 對 active-unexpired 回 true。
- pending/rejected/future/expired/revoked 回 false。
- entry verifier 可解析 ORG-A/ORG-B local reference，但不建立 Session/context。

004 實作後再加入：

- `POST /v1/auth/liff/exchange` 只有 active-unexpired 才原子建立 Session/context。
- 其他狀態建立 Session/context 數為 0。
- 到期／撤銷後原 context 下一個 request 立即失效。

## SC-001／SC-002 人工計時驗收

計時前固定版本、fixtures、網路環境與支援裝置，逐次記錄匿名 participant id、裝置／LINE 平台、開始／結束時間、是否第一次成功、是否需要研究人員介入、錯誤碼與觀察。研究人員可朗讀任務目標，但開始後不得提示按鈕位置、替代操作或排錯。

### SC-001 志工低門檻報名

- 至少 20 位未使用過 StrayHub 志工流程的參與者；至少 10 次 iOS LINE、10 次 Android LINE。
- 每人使用獨立、可重設的 LINE/application fixture，從掃描 QR 或點擊收容所專屬入口開始計時，到正確收容所的 pending 成功頁完整顯示停止。
- 第一次成功定義為未重啟流程、未更換 fixture、未由研究人員介入且只建立一筆 pending Application。
- 通過門檻：至少 18/20 在 120 秒內完成，至少 19/20 第一次成功；任何受保護資料提前顯示都直接判定失敗。

### SC-002 管理員 100 筆批次

- 至少 3 位具收容所管理工作情境的參與者；每人使用獨立 100 筆 pending fixture。
- 從 `/volunteers/applications` 資料可互動開始計時，到 batch 完整結果摘要可檢查停止。
- 任務固定包含狀態／時間篩選、目前結果全選、共同期限、10 筆指定個別期限覆寫、確認與逐筆結果檢查。
- 通過門檻：每位皆在 5 分鐘內完成，選取 target、期限與逐筆結果正確率均為 100%；API/Playwright latency 僅作診斷，不取代人工證據。

## 完整品質 Gate

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
npm --prefix packages/contracts run check
npm --prefix apps/web run quality
npm --prefix apps/web run build
npm --prefix apps/web run test:e2e:p0
npm --prefix apps/web run test:a11y:browser
npm --prefix apps/web run test:visual
./scripts/verify_local.sh
```

完成條件：

- 27 項 Functional Requirements 與 15 項 Success Criteria 都有自動化或明確人工證據。
- 100 筆人工 batch 與 1,200 筆全選 snapshot/chunk、partial success、stale version 與 idempotent retry 全部可重現。
- expiry／revoke／user-org disable request enforcement 即時；即使沒有後續 request，Worker/Audit/context cleanup 仍在 60 秒 SLA 內收斂。
- pending/rejected/withdrawn/future/expired/revoked 不會讀寫受保護資料。
- 跨 organization list/count/id guess/batch/notification 洩漏為 0。
- notification failure 不回滾或重放 domain decision。
- PLATFORM_ADMIN 缺少 target/reason 的成功率為 0，合法 read/write Audit 覆蓋率為 100%。
- SC-001／SC-002 人工計時樣本、原始記錄與 pass rate 可供 reviewer 重算。
- 原始 Draft／Report／Media／Audit 全部保留。
- P0 不使用 production credential，不等待 004 route UI 或任何 P1 功能即可獨立展示。
