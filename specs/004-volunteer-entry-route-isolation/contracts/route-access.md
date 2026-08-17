# UI／流程契約：角色導向入口與管理路由隔離

本文件定義使用者、輔助科技與自動化測試可觀察的 route 行為，以及 LIFF exchange 的 transaction 結果。前端 redirect 只縮小可見性，不取代 FastAPI authorization、Membership/Grant predicate 或 PostgreSQL RLS。

## 1. 正式收容所專屬入口

正式 URL 形態：

```text
https://<LIFF host>/volunteer-entry?entry=<opaque-shelter-entry-reference>
```

所有一般收容所共用同一個 LINE Official Account、Messaging API channel、Webhook 與 LIFF App。ORG-A／ORG-B 的差異只在 entry reference；不得建立每 shelter 的 LIFF credential 或 client-side role。

### Bootstrap 順序

1. 顯示「正在開啟 LINE 志工入口」的安全 status，不掛載 animals/draft/management children。
2. 從 server runtime config 取得 `LIFF_ID`，執行 `liff.init()`。
3. 外部瀏覽器若未登入，使用 LIFF login flow；返回後重新初始化。
4. 以 `liff.getIDToken()` 取得 raw token；不得把 decoded profile 送 server。
5. `POST /v1/auth/liff/exchange`，body 只含 `id_token + shelter_entry_reference`。
6. 成功後保存既有 auth tokens、Session id 與 transient LIFF recovery hint。
7. 重新取得後端 Active Context／scoped organization label，`replace('/animal-confirmation')`。

缺少 entry、LIFF 設定錯誤、初始化失敗、使用者取消登入或無 raw token 時，顯示繁中安全錯誤與「重新進入」「回到 LINE」，不得呼叫 protected API。

## 2. LIFF exchange transaction contract

後端固定順序：

1. digest raw entry，以 005 fixed-purpose resolver 取得候選 organization，立即設定該 organization RLS scope。
2. 驗證 raw LINE id token，取得 line user id。
3. 驗證 active LineUserBinding、active User 與 active Organization。
4. 只查候選 organization 的 exact Membership；必須是 `VOLUNTEER`、active、已開始、未到期，且有同 organization／Membership 的 active Grant。
5. 鎖定 Membership/Grant，以 database time 重做 effective predicate。
6. 建立 `SessionRecord(user_id, active_organization_id=候選 organization)`。
7. 建立 Refresh Token record 並簽發 access token。
8. 同一 transaction commit 後才回既有 AuthResponse。

### 失敗矩陣

| 狀態 | 結果 | 禁止結果 |
| --- | --- | --- |
| entry 無效／撤銷／purpose 不符 | 安全 403 | 不揭露 organization 是否存在 |
| LINE token 無效／過期／audience 不符 | 安全 401 | 不查 Membership、不建立 Binding |
| Binding 缺少／停用 | 安全 403 + 綁定／報名下一步 | 不自動建立 Binding |
| User 或 Organization 停用 | 安全 403 | 不建立 Session/context |
| 沒有申請／pending／rejected | 安全 403 + 等待／報名下一步 | 不建立 Membership |
| future Membership/Grant | 安全 403 + 尚未開始 | 不提早建立 context |
| expired／revoked／disabled／缺 Grant | 安全 403 + 重新報名／聯絡管理者 | 不延長或重新啟用 |
| ORG-A entry + ORG-B-only access | 安全 403 | ORG-A/ORG-B Session/context 都為 0 |
| database/dependency failure | 503 + 重試 | 不留下 partial row |
| active-unexpired exact access | 200 | Session/context 不得分兩次 commit |

每個非 200 案例都必須 assert 新增 SessionRecord=0、RefreshTokenRecord=0、Active Context=0，且 Application/Membership/Grant mutation=0。

## 3. 既有介面依賴

| Interface | 用途 | 本功能限制 |
| --- | --- | --- |
| `POST /v1/auth/login` | local Web/LIFF fixture Session + organizations/role | context 成功後依 selected role 導向；正式志工不使用帳密 |
| `POST /v1/auth/liff/exchange` | 正式 identity + entry exchange | 唯一 additive request；原子建立 Session/context |
| `GET /v1/auth/me` | profile/platform role/Memberships | deep link/reload 的 role 來源；client cache 不取代 |
| `GET /v1/auth/active-shelter-context` | server Session context | protected children 掛載前必須通過 |
| `PUT /v1/auth/active-shelter-context` | local/management context switch | 成功後才換資料；失敗保留仍有效舊 context |
| `GET /v1/organizations` | scoped organization label/management selector | volunteer 只在 auth/context 通過後取 label；management 只在 role 通過後載入 |
| `GET /v1/animals` | 今日可回報動物 | volunteer boundary 通過後載入 |
| `GET /v1/line/care-report/drafts/current` | 單一 current draft | context 通過後載入 |
| management page APIs | Dashboard/animals/reports/settings 等 | 志工 request count 必須為 0 |

直接呼叫 management API 的志工仍必須由後端拒絕；UI redirect 成功不代表 API 已授權。

## 4. 登入目的地

### Local fixture

1. credential login 成功後保存 Session。
2. 使用者完成既有 Active Shelter Context 選擇。
3. `PUT /active-shelter-context` 成功後，依 selected organization 的 server role：
   - `VOLUNTEER` → `replace('/animal-confirmation')`
   - `STAFF`／`SHELTER_ADMIN`／`PLATFORM_ADMIN` → `replace('/')`
4. Context 建立失敗停留在登入流程，不宣稱已進入任何工作台。

正式志工一律使用前述 LIFF bootstrap，不輸入 StrayHub 帳密。

## 5. 有效角色與 context

Deep link、reload、browser back 與 recovery 成功後必須重取 profile/context：

- `user.platform_role == PLATFORM_ADMIN` → `PLATFORM_ADMIN`。
- 其他使用者只採 `membership.organization_id == activeContext.organization_id` 的 active Membership role。
- 找不到 matching Membership 時，不得 fallback 為 `STAFF` 或使用 sessionStorage role。
- URL entry、pathname、organization cache、QR、動物名稱與 shelter number 都不能改變 effective role/context。

## 6. Route access matrix

| Route area／代表 route | `VOLUNTEER` | `STAFF` | `SHELTER_ADMIN` | `PLATFORM_ADMIN` |
| --- | --- | --- | --- | --- |
| `/`、`/animals/**`、`/reports/**` | 導回 `/animal-confirmation` | 允許 | 允許 | 有 context 後允許 |
| `/ai-review`、`/care-calendar` | 導回志工入口 | 依既有 API 權限 | 依既有 API 權限 | 依既有 API 權限 |
| `/settings/**`、`/volunteers/**`、`/shelters` | 導回志工入口 | 依既有 API 權限 | 依既有 API 權限 | 依既有 API 權限 |
| 任何未來 `(management)` child route | 導回志工入口 | 依既有 API 權限 | 依既有 API 權限 | 依既有 API 權限 |
| `/animal-confirmation`、`/care-report` | 有 Session/context 後允許 | 不新增反向限制 | 不新增反向限制 | 有 context 後不新增反向限制 |
| `/volunteer-entry?entry=…` | 公開 bootstrap | 公開 bootstrap | 公開 bootstrap | 公開 bootstrap |

Query、hash、尾端斜線、dynamic id、reload 與 browser history 不改變 route area。公開 bootstrap 不顯示任何 protected data。

## 7. Management request ordering

1. 顯示「正在確認登入角色與目前收容所」。
2. 只取得 `/auth/me` + `/auth/active-shelter-context`。
3. 推導 effective role。
4. 志工：不掛載 Management Shell/children，顯示 redirect status 並 replace 到 volunteer entry；organizations、Dashboard 與 page-specific management request 全為 0。
5. 管理角色：才取得 organizations，掛載 Shell，再掛載 child 並開始 page request。

`/` 必須由 `(management)` route group 接管，不可保留第二套先掛載 Dashboard 的 composition。

## 8. Volunteer request ordering與 shelter label

1. 顯示 Session/context checking status。
2. 取得 profile + Active Context 並確認 matching role/access。
3. 取得 scoped organization label；context cycle 未完成前不得顯示前一 shelter label。
4. 才掛載 volunteer child。
5. `/animal-confirmation` 可並行讀 animals + current draft；`/care-report` 沿用 current draft/save flow。

兩頁都必須清楚顯示目前收容所名稱。context/recovery 改變時先移除舊 protected view，全部重新驗證後才顯示新資料。

## 9. Active draft resume

### 沒有 current draft

- 直接顯示今日名單、QR 與 shelter number 搜尋。
- 不顯示空 prompt。

### 可恢復

- 必須 active、未過期、同 Active Context，且 animal 在今日授權名單。
- 顯示 animal name、可用時顯示 shelter number、繁中 progress。
- 「繼續回報」→ `/care-report`，由後端重讀 current draft。
- 「稍後處理」→ 留在 `/animal-confirmation`；不得 cancel/delete/modify Draft。

### 不可恢復

- 不顯示答案、其他 tenant animal/detail 或 stale shelter label。
- 顯示安全 unavailable + 重試／聯絡管理者。
- 不自動切換 context，不刪歷史資料。

## 10. Session 401 與 single-flight recovery

### Local/management session

- protected 401 → clear auth → `replace('/login')`。
- 不執行 LIFF exchange。

### Formal LIFF session

1. 第一個 protected 401 建立 recovery epoch，卸載 protected children。
2. 並行 401 共用同一 in-flight Promise；exchange request count 仍為 1。
3. 以已初始化 LIFF 的 raw ID token + transient original entry reference exchange。
4. 成功：重取 profile/context/label，回到原 volunteer pathname；不回到被拒 management deep link。
5. 原 request 若為 mutation，不自動重播；保留可恢復輸入並要求明確重試。
6. exchange 失敗、缺 token/reference、或恢復後再次 401：terminal state，停止自動 request/navigation，顯示「重新進入」「回到 LINE」。

每個 epoch `exchangeAttempts <= 1`；測試必須同時觀察 exchange count 與 navigation count。

## 11. Context switch failure

- management 使用者切換成功後才卸載舊 context 並載入新資料。
- switch 失敗時，保留後端仍確認有效的舊 context 與舊 view，顯示錯誤並可重試。
- 不把任何新 context 的部分 organizations/page response 合併到舊 view。
- 若舊 context 也已失效，進入不含 protected data 的 context-required/重新登入狀態。

## 12. LINE Bot regression

- 已有有效 organization context：先提供該 shelter 可回報狗狗選擇。
- context 未確認、多個可能 context 或有效 Membership 不唯一：先進入既有 LIFF/context verification。
- 不以 dog name、shelter number、client state 或轉傳 URL 推測 tenant。
- 不修改 Webhook Signature、Event Idempotency 或 Conversation State Machine schema。

## 13. 可及性與響應式

- initializing、logging-in、exchanging、checking、redirecting、recovering、context-required、error 與 terminal 都有繁中 title、description、next action。
- Loading/recovery 使用 polite status；阻斷錯誤使用可讀取 alert，避免重複播報。
- 「繼續回報」「稍後處理」「重試」「重新進入」「回到 LINE」可鍵盤操作並有可見 focus。
- 360px 下長中文、shelter name、draft prompt 與 error actions 不截斷、不重疊、不產生非必要水平捲動。
- 不只以 color/icon/animation 表達狀態；reduced motion 不影響理解。

## 14. 驗收證據

P0 至少留下：

- canonical OpenAPI + generated type drift 為 0。
- exchange success/entry/identity/access/concurrency/failure matrix，失敗 partial state 為 0。
- ORG-A／ORG-B exact context 與 cross-entry isolation tests。
- 4 角色 local login destination matrix。
- 志工對全部 `(management)` route 的 deep link/reload/back 結果，management request count=0。
- no/resumable/unavailable draft 與 save failure。
- local 401 與正式 LIFF single-flight 401 matrix；每 epoch exchange <=1、loop=0。
- 既有 LINE Bot context/dog-first regression。
- 360/768/1024/1440、keyboard、axe 與 reviewer-approved visual evidence。
- 同一受控 LINE OA/channel/Webhook/LIFF App 的 ORG-A/ORG-B 專屬 URL、正確 context、跨收容所拒絕及 360px 實機證據。

Browser mock 不取代真實後端 security/isolation 或受控 LINE／LIFF 驗收；受控 evidence 不得保存 raw token/reference、LINE user id 或其他個資。
