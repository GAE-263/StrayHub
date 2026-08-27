# Research：志工報名與限時授權

## 研究範圍

本研究依 [spec.md](spec.md)、Constitution 3.0.0 與現有 StrayHub 程式碼收斂 P0 技術設計。現況為 FastAPI + SQLAlchemy async + PostgreSQL + Alembic、Next.js App Router，以及共用 LINE identity／Messaging API adapter；`OrganizationMembership` 目前只有 role/status，Session 與 Webhook Session 已保存 organization context，但尚未檢查 Membership 時間範圍；Worker 入口存在但目前僅有基礎 loop。

## 決策 1：Membership 保存目前有效期，Grant Cycle 保存不可覆寫歷史

**決策**：維持資料庫既有 `UNIQUE (organization_id, user_id)`，每位使用者在單一收容所只有一筆 `OrganizationMembership`。為 Membership 新增 nullable `valid_from`、`expires_at`、`access_version`；只有 `VOLUNTEER` 必須有有效且有限的時間範圍。另新增 `VolunteerAccessGrant`，每次核准／重新授權建立新週期，保存來源 application、原始開始／到期、目前狀態、撤銷資訊與版本。新 organization 必須在 organization create transaction 內同步建立 168 小時初始 `OrganizationVolunteerAccessPolicy`，不得依賴首次 GET lazy-create。

目前 authorization 直接讀 Membership 投影；Grant 是歷史與稽核來源。核准、重新授權、期限調整或撤銷必須在同一 transaction 同步更新 Membership、目前 Grant、Audit 與 Notification outbox，避免兩套正式狀態分歧。

**理由**：

- 現有 authentication、context 與多數 endpoint 已以 Membership 為 hot-path；擴充欄位比全面改成另一種 join model 風險小。
- unique Membership 可保留既有帳號、角色與 context 關聯；Grant Cycle 則符合「重新授權不得覆寫前次歷史」。
- 管理角色不需要限時，因此時間欄位保持 nullable；DB constraint 只強制 `VOLUNTEER`。

**考慮過的替代方案**：

- **每次核准建立新的 Membership row**：不採用；會破壞既有 unique constraint，並讓 request context 不知道哪一筆是目前角色。
- **只在 Membership 上覆寫日期**：不採用；無法完整證明每次重新授權與期限調整前的狀態。
- **只在 Grant 上保存日期、每個 request 都找最新 Grant**：不採用；可以實作，但會讓既有所有 Membership authorization 路徑同時承擔 history query，且較難逐步遷移。

## 決策 2：既有 VOLUNTEER 採有限期、可追溯的 migration backfill

**決策**：rollout 拆成 0024 expand 與 0025 backfill/enforce。0024 先為每個 organization 建立 `OrganizationVolunteerAccessPolicy`（初始值 168 小時）與 nullable schema；若收容所需要不同過渡窗口，部署者可在兩階段間以受控 script 設定 policy。0025 只為當時有效且無到期時間的既有 `VOLUNTEER` Membership 建立 `legacy_migration` application 與 grant。`valid_from` 為同一 migration transaction timestamp，`expires_at` 依該 Membership 所屬 organization 在遷移當下的 `default_grant_duration_hours` 計算；Grant 另快照 `policy_version_used` 與 `duration_hours_used`，Membership access version 從 1 開始。Disabled、revoked、expired 或其他非有效 Membership 保持原狀，不建立 synthetic Application／Grant，不改變角色或狀態；migration validation 必須證明這些 Membership 沒有被啟用或產生授權週期。Audit reason 明確標記「既有 Membership 限時化遷移」，actor reference 為 `SYSTEM_MIGRATION`，不冒充管理員。

部署前需由營運匯出清單，並通知各收容所管理員在各自 policy 所定窗口內確認、延長或撤銷。Rollback 只回復 schema／程式版本；若已產生新的申請或授權決策，不以 downgrade 刪除正式歷史，而採 forward fix。

**理由**：

- 把既有志工留成無期限會直接違反 P0 的安全不變條件。
- 立即全部停用會造成不可預期的現場中斷；使用 organization 當時 policy 可維持有限窗口，也符合收容所可管理預設期限的最新決策。
- migration 是既有授權的資料轉換，不是 runtime 自動核准規則。

**考慮過的替代方案**：

- **既有資料永久 grandfather**：不採用；形成無期限安全例外。
- **migration 時立即撤銷所有志工**：不採用；雖最保守，但會中斷正在進行的照護，且沒有給管理員遷移窗口。
- **所有 organization 一律遷移 168 小時**：不採用；會忽略收容所已設定的 policy，與最新澄清衝突。

## 決策 3：收容所 entry reference 只解析候選 organization

**決策**：LIFF onboarding 的 status/apply/withdraw request 都帶 LINE id token 與 opaque `shelter_entry_reference`。正式 reference 是至少 256-bit 的隨機值，資料庫只保存 SHA-256 digest、organization、purpose、status 與 rotation metadata。因 pre-context request 尚不知道 organization，runtime 不取得 entry table 的跨租戶 SELECT；`ShelterEntryReferenceVerifier` 只能呼叫固定 `search_path`、固定輸出欄位的 `SECURITY DEFINER` resolver，以 digest + purpose 換取 active reference id 與候選 organization id，再立即設定 organization scope並檢查收容所 active。申請入口 active 只作為 submit gate；既有 applicant 的 status 不因 `applications_enabled=false` 被隱藏。reference 不含角色、Membership 或授權結果，也不能直接建立 Session/context。

P0 local fixture 提供 deterministic reference；正式 reference 由平台管理流程為單一 organization 發行，rotation 先建立新 active reference、更新 QR／Rich Menu 入口，再撤銷舊 reference。因 reference 不是權限憑證，可保留短暫雙 active 發布窗口；撤銷後舊連結只回安全停用狀態。這個 port 同時是 004 後續擴充 LIFF exchange 時的整合邊界。

**理由**：

- 志工可從專屬 URL 直接知道本次報名哪個收容所，不必在共用清單搜尋。
- 即使 URL 被轉傳，最多只能讓另一個已驗證 LINE user 對同一收容所提出 pending 申請；不能看資料或自動取得權限。
- 高熵 opaque token、digest-at-rest 與 purpose 可避免 client 任意把裸 organization id 解釋成內部 reference，也能逐 organization 撤銷／輪替；真正安全性仍由後端狀態與管理員決策提供。

**考慮過的替代方案**：

- **每個收容所獨立 LIFF App／LINE OA**：不採用；增加憑證、Webhook、Rich Menu、部署與支援成本，且屬 P1。
- **只接受裸 organization id**：不採用；雖不會直接授權，但容易被猜測、誤用並耦合內部主鍵。
- **自包含簽章 reference**：不採用；可避免資料庫 lookup，但逐 organization 撤銷與輪替較複雜，而且不能像既有 QR token pattern 一樣只保存 digest。
- **entry reference 即為授權 token**：不採用；轉傳連結會繞過人工核准。

## 決策 4：首次報名原子建立身分綁定，但不建立 Membership

**決策**：application service 驗證 LINE id token 後，以 `line_user_id` unique constraint 查找 binding。status/withdraw 只能重用既有 Binding；未知 LINE identity 只查 status 時不得建立 User、Binding、Membership 或 Session。只有 submit 可在同一 transaction 建立 password-less `User`、active `LineUserBinding` 與 pending `VolunteerApplication`；存在時重用 active user。partial unique index 保證同一 user／organization 只有一筆 pending；`client_request_id` 提供 request-level idempotency。`applications_enabled=false` 只阻止 submit；既有 applicant 的 own-status query 仍可在 organization/user active 且 reference 有效時執行。

若 concurrent requests 同時建立 binding 或 pending，捕捉 unique violation、重新讀取既有紀錄並回傳同一申請狀態。任何步驟失敗都回滾 User／binding／application，且不建立 Membership。

**理由**：

- pending 使用者需要可追蹤的 platform identity，但還沒有任何租戶資料權限。
- DB unique constraint 是多 process／多 request 下的最終一致性防線，不能只靠前端 disable button。
- 每次 status/withdraw 都重新驗證 LINE id token，不額外發出可長期使用的 pre-approval Session。

**考慮過的替代方案**：

- **報名時建立 disabled Membership**：不採用；會讓既有查詢、計數與授權 helper 誤把 pending 視為組織成員。
- **pending 前建立一般 StrayHub 登入 Session**：不採用；增加 token lifecycle，且容易與正式 Membership session 混淆。

## 決策 5：Application 與 effective access 分離

**決策**：Application 狀態只使用 `pending`、`approved`、`rejected`、`withdrawn`。核准後 application 保持 approved；是否尚可使用由 Membership + current Grant 的狀態與時間推導為 `upcoming`、`active`、`expired` 或 `revoked`。志工 status response 將兩者分開回傳並產生對應下一步。

重新報名只允許在沒有 pending、且前次 rejected／withdrawn／expired／revoked 時建立新 Application，透過 `previous_application_id` 串接；重新核准建立新 Grant，不改寫舊 Grant。

**理由**：申請決策和時間性授權是不同事實。把 application 在到期時改成 expired 會抹去「當時確實核准」的歷史，也會讓 regrant 難以對帳。

**考慮過的替代方案**：

- **單一 status 欄位涵蓋所有狀態**：不採用；會混合審核與授權生命週期，產生不合法 transition。

## 決策 6：批次審核採持久化 orchestration 與逐項 transaction

**決策**：batch request 必須帶 caller 產生的 `operation_id`，並選擇兩種互斥 target 模式：

- `explicit_items`：caller 列出 1..500 個 `application_id`、`expected_version` 與可選期限覆寫。
- `all_filtered`：caller 提交目前 organization 的 pending filter 與可選個別覆寫；server 在建立 Batch 的同一個 repeatable-read transaction 重新執行不含 pagination 的 tenant-scoped query，將確認當下所有 matching application id/version 寫成不可變 `VolunteerDecisionBatchItem` snapshot。確認 transaction 完成後才新增或才符合 filter 的申請不會被納入。

服務以 organization + operation id 建立或取得 `VolunteerDecisionBatch`。`requested_count` 不設 500 上限；orchestrator 每次以 `FOR UPDATE SKIP LOCKED` claim 最多 500 個 pending items，再用獨立 transaction 逐項：

1. 設定 organization RLS scope。
2. 以 `SELECT ... FOR UPDATE` 取得 application。
3. 驗證 tenant、pending 狀態與 `expected_version`。
4. approve 時建立／啟用 VOLUNTEER Membership、建立新 Grant；reject 時只結案 application。
5. 寫入 item result、per-target Audit 與 Notification outbox，commit。

已完成 item 不重做；conflict／validation failure 保留原狀並記錄安全錯誤碼。Batch 保存 selection mode、normalized filter snapshot、policy version/duration snapshot、target count、claimed/processed counts 與結果。程序中斷時，重送同 operation id 或 Worker 恢復只處理尚未 terminal 的 items；同一邏輯 Batch 最後寫入 `completed_with_errors` 或 `completed`。UI 對 100 筆人工情境提供全選與結果摘要，對 1,200 筆以上顯示非同步進度並以 cursor 取得逐項結果。

**理由**：

- 一個 request transaction 加 savepoint 仍會在最後 commit 失敗時失去全部成功項目；逐項 commit 才真正符合 partial success。
- operation record 讓 HTTP retry、程序中斷與管理畫面 reload 都能恢復同一結果。
- `expected_version` 阻止舊畫面覆寫其他管理員較新的決策。
- server-side snapshot 讓「目前篩選結果全部」真正跨頁，並避免把確認後新增申請意外納入；500 只是內部分段，不改變使用者選擇語意。

**考慮過的替代方案**：

- **all-or-nothing transaction**：不採用；一筆衝突會讓已可處理的 99 筆全部失敗。
- **只用前端檢查 updated_at**：不採用；無法避免提交與 commit 之間的 race。
- **同步逐項但不存 Batch**：不採用；network retry 可能重複決策，也沒有可對帳摘要。
- **全選只處理前 500 筆或目前頁面**：不採用；與已澄清的完整篩選結果語意衝突，並提高管理員重複操作成本。

## 決策 7：request-time expiry 是安全邊界，Worker 是狀態收斂器

**決策**：所有 organization-protected request、Active Shelter Context switch、LIFF exchange 與 Webhook Session resolution 共用 effective predicate：

```text
role != VOLUNTEER
OR (
  membership.status == active
  AND membership.valid_from <= now
  AND now < membership.expires_at
  AND current grant 未撤銷
)
```

對 VOLUNTEER 不符合條件時，request 立即拒絕；若 Session 的 active organization 正是失效 organization，清除該 context，並使 organization-scoped Webhook Session 失效。不得因 access token 本身尚未過期而繼續使用資料。

Worker 最多每 60 秒掃描 due grants、inactive organizations 與 disabled users，逐 organization transaction 把 Grant/Membership 狀態收斂、清除相關 context、寫 Audit、enqueue 適用通知。organization/user 停用的既有管理 transaction 也應嘗試同步清理，但 Worker 必須在沒有後續 request 或同步清理中斷時補償收斂。重複 sweep 必須冪等；即使 Worker 停止，request-time predicate 仍不會延長權限。

**理由**：

- 只依賴 cron/worker 會有至少一個排程窗口的越權風險，也無法保障 worker outage。
- 只做 request-time derived state 雖安全，但無法滿足自然到期 Audit、管理列表與通知的一分鐘收斂要求。

**考慮過的替代方案**：

- **只靠 Worker 改 status**：不採用；worker 延遲時 expired Membership 仍可能被讀成 active。
- **到期時刪除 Session、Membership 或 Draft**：不採用；破壞歷史與原始資料，而且跨收容所 user 可能仍有其他有效 context。

## 決策 8：撤銷只終止目標 organization context

**決策**：撤銷、縮短至現在以前或自然到期時：

- Membership/Grant 立即失效。
- `SessionRecord.active_organization_id == target organization` 時清為 null，而不是撤銷整個 user Session。
- target organization 的 active `WebhookSession` 標為 revoked/expired。
- access/refresh token 可繼續代表已驗證 user，但不能在失效 organization 建立 context；若 user 有其他有效 Membership，可重新選擇其他收容所。
- Draft、Care Report、Media、Audit 與 LINE binding 均不刪除。

**理由**：同一志工可跨收容所協助。整個登出會錯誤中斷其他仍有效的 organization，也不比清除受影響 context 更安全。

**考慮過的替代方案**：

- **撤銷 user 所有 Session 與 refresh family**：不採用；權限是 tenant-scoped，不應擴大成 platform identity revoke。
- **只等下次 context switch 才發現失效**：不採用；已存在 context 仍可能繼續送 request。

## 決策 9：通知使用 transactional outbox，永不決定授權

**決策**：Application submit/withdraw、approve/reject、期限變更、expire/revoke 成功時，在同一 business transaction 寫入 `VolunteerNotificationDelivery`。Worker 以 `FOR UPDATE SKIP LOCKED` claim，使用 LINE push 或 local mock adapter 傳送；每個 domain event 有唯一 idempotency key。失敗記錄 attempt count、last error、next attempt，並以 bounded exponential backoff 重試。

管理後台提供獨立的 organization-scoped 通知失敗清單，涵蓋所有 event type，而不是只掛在 Grant 詳情。SHELTER_ADMIN 可依 event type、failed time 與 status 篩選，選取單筆或多筆 failed delivery 送入 retry queue；每次 retry request 以 `operation_id` 冪等，只更新 delivery/attempt，不重放 Application、Membership 或 Grant mutation。永久失敗仍保留並顯示安全錯誤摘要。

API 與 UI 永遠從 CRM Application/Membership/Grant 顯示正式結果，不從 notification status 反推；通知失敗不回滾決策，也不建立第二個 Membership。

**理由**：LINE 是外部服務且可能被封鎖、限流或暫時失效。Outbox 能同時保證正式決策落地與後續可觀察／重試，不需跨 PostgreSQL + LINE distributed transaction。

**考慮過的替代方案**：

- **API transaction 內同步 push，失敗則 rollback**：不採用；把外部服務可用性變成授權一致性的必要條件。
- **只記 log、不存 delivery 狀態**：不採用；無法可靠重試或讓管理員判斷哪些通知失敗。
- **只在 Application／Grant 詳情顯示失敗**：不採用；報名送出、拒絕、撤回等事件不一定有 active Grant，且管理員無法一次發現與批次重試。

## 決策 10：授權 API 與 UI 都以 organization scope 為第一層邊界

**決策**：管理 API 使用 `/v1/organizations/{organizationId}/volunteer-*`，但 path id 只是候選 scope：SHELTER_ADMIN 必須有相同 Active Shelter Context；PLATFORM_ADMIN 的角色本身是平台明確授權，但每個 volunteer management read/write request 都必須指定單一 organization，並提供 trim 後 1..500 字的 `X-Platform-Support-Reason`。缺少 target 或 reason 時，在 query 前拒絕且不設定 platform scope。完整 Audit lifecycle 是所有 management endpoint 的前置 foundation，必須涵蓋成功、拒絕、not-found、validation failure 與 exception result，不能延後到通知或 isolation story 才補上。

通過 gate 後呼叫新的 `set_platform_support_scope(target_organization_id)`：同時設定 platform actor 與 `app.current_org_id`，本功能 RLS policy 即使在 platform mode 也要求 row `organization_id` 等於 current org，不直接沿用可讀取所有 tenant 的一般 `set_platform_scope()`。每次 read 與 mutation 都建立 `platform_support.accessed` 或對應 mutation Audit，包含 actor、target organization、resource type/id（如適用）、reason、operation id 與 result。SHELTER_ADMIN 不需 support reason；STAFF、VOLUNTEER 與其他 organization actor 一律拒絕。repository query 仍同時帶 organization id，形成 service + query + RLS 三層隔離。

跨租戶 id、缺少資源與不可存取資源對非平台 actor 使用相同不洩漏回應；列表、counts、batch results、notifications 與 Audit 都不能混入其他 organization。

**理由**：path 與 UI 隱藏都不是安全邊界；application/membership id 為 UUID 也不能取代 actor scope 與 RLS。

**考慮過的替代方案**：

- **平台管理員預設跨租戶列表**：不採用；規格只允許明確授權的 organization support。
- **只靠 ORM where，不加 RLS**：不採用；不符合 Constitution 的資料存取層隔離要求。
- **另建 organization-specific PLATFORM_ADMIN grant**：不採用；最新澄清明定 PLATFORM_ADMIN 角色即授權，P0 以每 request 單一 target、reason 與 Audit 作補償控制。

## 決策 11：onboarding route 與既有 volunteer protected route 分開

**決策**：新增 `/volunteer-application`，放在不要求 Membership 的 `(volunteer-onboarding)` route group，但頁面只能透過後端 LINE identity + entry reference contract 取得自己的申請狀態。它不能呼叫 animals/drafts/reports API。管理頁新增 `/volunteers/applications`、`/volunteers/access` 與 `/volunteers/notifications`，沿用 Management Shell 且只有 SHELTER_ADMIN／PLATFORM_ADMIN 顯示入口；通知頁是 organization 統一失敗清單，不依附特定 Application 或 Grant。

核准成功後 onboarding 顯示到期時間與「進入照護流程」下一步；實際建立 Session/context 由 004 的 LIFF exchange 完成，005 不在前端偽造 access。pending/rejected/expired/revoked 則只顯示安全狀態與適用動作。

**理由**：pending 使用者沒有 Membership，不能放在 004 的 protected volunteer layout；同時仍需阻止頁面在身分解析前載入任何受保護內容。

**考慮過的替代方案**：

- **把 onboarding 放進 `/animal-confirmation`**：不採用；會混淆「尚未授權」與「可讀取動物」的 route boundary。
- **核准後由 005 直接建立 context**：不採用；Session/context 與 route recovery 已由 004 明確負責。

## 決策 12：時間、版本、錯誤與可及性 contract 固定化

**決策**：

- DB 與 API date-time 使用 UTC-aware timestamp／RFC 3339；UI 以台灣時區顯示完整日期時間與剩餘期限。
- 新 organization policy 初始為 168 小時（管理 UI 顯示 7 天）；未覆寫的日期型申請使用 decision batch 建立時所快照的 organization policy duration，自所選服務日期的 organization 當地午夜起算。policy 更新只影響後續建立的 decision batch，不回寫既有 grant。
- 一份申請可包含多個獨立審核的服務日期；第一個核准日期建立該 application 唯一的 grant，後續日期只更新日期審核狀態，不另建或延長 grant。沒有服務日期的歷史申請若要核准，管理員必須明確提供開始時間。
- `expires_at` 必須嚴格大於 `valid_from`；縮短到 `now` 或以前需 `confirm_immediate_expiry=true`，並走立即失效流程。
- Application 與 Grant response 帶 integer `version`；mutation 必須帶 expected version。
- 409 表示 stale version／同一 operation payload 不一致；422 表示日期或原因 validation；404/403 避免資源存在性洩漏。
- 管理 batch UI 使用 table + checkbox、select-all filter summary、per-row override、確認 dialog、完整 snapshot count、進度與 cursor 分頁逐項結果；360px 轉為可捲動／堆疊資訊，但不把 checkbox、期限或錯誤只靠顏色表達。

**理由**：這些細節直接影響 7 天語意、並行安全、重試與驗收可重現性；若留給各頁自行解讀會產生不同結果。

**考慮過的替代方案**：

- **永久固定 168 小時預設**：不採用；最新規格允許每個 organization 修改預設。
- **以台灣曆日午夜計算**：不採用；會讓同樣的「7 天」因核准時間而得到不同時數。
- **由 client 保存全選 target**：不採用；容易受分頁、stale state 與 payload 大小影響，不能保證確認時完整 snapshot。

## 決策 13：SC-001／SC-002 使用受控人工計時，不以 API latency 代替

**決策**：SC-001 使用至少 20 位未使用過 StrayHub 志工流程的測試參與者，從掃描／點擊收容所專屬入口開始計時，到 pending 成功頁完整顯示停止；測試中不得由研究人員代操作或口頭引導。至少 18/20（90%）須在 120 秒內完成，至少 19/20（95%）須在第一次流程中成功，不得重啟或由研究人員排錯。裝置至少各含 10 次 iOS LINE 與 Android LINE 測試。

SC-002 使用至少 3 位具收容所管理工作情境的測試管理員，各自操作獨立的 100 筆 pending fixture；從申請頁資料可互動開始，到完整結果摘要可檢查停止。流程包含篩選、目前結果全選、共同期限、10 筆指定個別覆寫、確認與結果檢查；每位皆須在 5 分鐘內完成，且選取／期限／逐筆結果正確率為 100%。API performance test 只作診斷證據，不取代人工計時。

**理由**：SC-001／SC-002 衡量的是低門檻與人工作業效率；若只量 API p95，無法證明使用者理解收容所、期限與批次結果。

**考慮過的替代方案**：

- **只用 Playwright wall-clock**：不採用；可作 regression，但不能代表第一次使用者的理解與操作時間。
- **只由開發者自行操作一次**：不採用；樣本不足且高度熟悉流程，會低估實際門檻。

## 已解決的未知事項

- 有效期間的正式位置：Membership current projection + append-only Grant history。
- 既有志工 migration：依 organization 當時 policy 建立有限 legacy window + `SYSTEM_MIGRATION` audit，不保留無期限例外。
- pending identity：建立／重用 User + LINE binding，不建立 Membership 或一般 Session。
- 收容所判定：可輪替、digest-at-rest 的 opaque entry reference 只解析候選 organization，不授權。
- 批次 partial success：顯式清單最多 500；全 filter server snapshot 不限分頁，持久化 batch/item 後每段最多 500 筆、逐項 transaction、operation id、row lock、expected version。
- 到期 enforcement：request-time 即時拒絕 + Worker 一分鐘內狀態收斂。
- Session scope：只清除失效 organization context，不撤銷其他 organization 權限。
- 平台支援：PLATFORM_ADMIN 角色即授權，但每 request 單一 target、必填原因，且 read/write 全稽核。
- 通知：transactional outbox + organization 統一失敗清單 + 單筆／多筆 retry；通知不是正式結果。
- 004 邊界：005 提供 effective Membership 與 entry verifier contract；004 建立 Session/context 與 route isolation。
- 驗證：DB constraints/RLS、Pytest 全層次、generated OpenAPI、Vitest/Playwright/axe/visual、local LINE mock，以及 SC-001／SC-002 受控人工計時。

本研究沒有未解決的設計問題。
