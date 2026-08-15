# UI 行為契約：角色導向入口與管理路由隔離

本文件定義使用者、輔助科技與自動化測試可觀察的 route 行為。它不取代後端 authorization，也不修改既有 HTTP schema。

## 1. 既有介面依賴

| Interface | 用途 | 本功能限制 |
| --- | --- | --- |
| `POST /v1/auth/login` | 建立 local Web Session 並取得可選 organization + role | 不修改 response schema；context 建立成功後才依 selected role 導向 |
| `POST /v1/auth/liff/exchange` | 既有 LIFF 身分交換 | P0 不新增真實 LINE deployment；交換結果遵循相同入口 policy |
| `GET /v1/auth/me` | 取得目前 user、platform role 與 Membership | deep link／reload 的角色來源；不得以 client cache 取代 |
| `GET /v1/auth/active-shelter-context` | 取得目前 Session 的 organization | 必須先通過才能掛載受保護 children |
| `PUT /v1/auth/active-shelter-context` | 建立或切換目前 context | 成功後才進行 role-directed navigation |
| `GET /v1/organizations` | 管理 Shell 的 context selector | 只有 management role 通過 boundary 後才能載入 |
| `GET /v1/animals` | 目前 context 的今日可回報動物 | volunteer boundary 通過後載入；同時提供 draft prompt 的動物辨識資料 |
| `GET /v1/line/care-report/drafts/current` | 目前 context 的單一 active draft | P0 恢復提示；null 代表沒有可恢復草稿 |
| `GET /v1/management/dashboard` | 管理首頁摘要 | 志工 route decision 完成前不得呼叫；志工 deep link request count 必須為 0 |

直接呼叫任何 management API 的志工仍必須收到既有後端拒絕；前端 redirect 通過不代表 API 已授權。

## 2. 登入目的地契約

完成 credential login 或既有 LIFF exchange 後：

1. Session 必須先保存。
2. 若有多個 organization，使用者必須先完成既有 Active Shelter Context 選擇。
3. `PUT /v1/auth/active-shelter-context` 成功後，才依選定 organization 的後端 role 決定目的地。
4. `VOLUNTEER` → `replace('/animal-confirmation')`。
5. `STAFF`、`SHELTER_ADMIN`、`PLATFORM_ADMIN` → `replace('/')`。
6. Context 建立失敗時留在登入流程，清除不可繼續使用的 client auth cache，顯示台灣繁體中文錯誤與重試方式。

登入按鈕與 context 確認文案不得一律宣稱「進入管理工作台」；文案必須適用於志工與管理使用者，或依 selected role 顯示正確目的地。

## 3. 有效角色契約

Deep link、reload 與 browser back 必須重新取得 profile/context：

- `user.platform_role === PLATFORM_ADMIN` → `PLATFORM_ADMIN`。
- 其餘使用者 → 找到 `membership.organization_id === activeContext.organization_id && membership.status === active`，使用該 Membership role。
- 找不到 matching Membership 時，不得 fallback 為 `STAFF` 或使用 sessionStorage role；結果為安全的 context/authorization state。

前端 role 只縮小 route 可見性；後端可以對單一管理功能施加更窄權限。

## 4. Route access matrix

| Route | `VOLUNTEER` | `STAFF` | `SHELTER_ADMIN` | `PLATFORM_ADMIN` |
| --- | --- | --- | --- | --- |
| `/` | 導回 `/animal-confirmation` | 允許 | 允許 | 有 context 後允許 |
| `/animals` | 導回志工入口 | 允許 | 允許 | 允許 |
| `/animals/[animalId]` | 導回志工入口 | 允許 | 允許 | 允許 |
| `/animals/[animalId]/timeline` | 導回志工入口 | 允許 | 允許 | 允許 |
| `/reports` | 導回志工入口 | 允許 | 允許 | 允許 |
| `/reports/[reportId]` | 導回志工入口 | 允許 | 允許 | 允許 |
| `/ai-review` | 導回志工入口 | 依既有 API 權限 | 依既有 API 權限 | 依既有 API 權限 |
| `/settings/*` | 導回志工入口 | 依既有 API 權限 | 依既有 API 權限 | 依既有 API 權限 |
| `/shelters` | 導回志工入口 | 依既有 API 權限 | 依既有 API 權限 | 依既有 API 權限 |
| `/animal-confirmation` | 有 Session/context 後允許 | 不新增反向限制 | 不新增反向限制 | 有 context 後不新增反向限制 |
| `/care-report` | 有 Session/context 後允許 | 不新增反向限制 | 不新增反向限制 | 有 context 後不新增反向限制 |

Query string、hash、尾端斜線、dynamic id 與 browser history 不能改變 route area 或繞過此 matrix。

## 5. Management request ordering

Management route 的可觀察順序必須是：

1. 顯示「正在確認登入角色與目前收容所」等安全 status。
2. 取得 `/auth/me` 與 `/auth/active-shelter-context`。
3. 推導有效角色。
4. 志工：顯示 redirect status 並 replace 到 `/animal-confirmation`；不發出 organizations、Dashboard 或 page-specific management request。
5. 管理角色：取得 organizations，掛載 Management Shell，再掛載 page children 並開始 page-specific request。

測試必須觀察 request URL，而不只檢查最終畫面。志工情境中的 `/v1/management/dashboard`、`/v1/management/animals*`、`/v1/management/reports*`、AI／setting／shelter management request 數必須為 0。

## 6. Volunteer request ordering

Volunteer route 的可觀察順序必須是：

1. 顯示安全的 Session／Context loading status。
2. 取得 profile + Active Context 並確認有效。
3. 才掛載 `/animal-confirmation` 或 `/care-report` children。
4. `/animal-confirmation` 可並行取得今日動物與 current draft。
5. `/care-report` 沿用既有 current draft 恢復與保存流程。

Boundary 通過前不得發出 `/v1/animals`、QR、draft 或 care report request。

## 7. Active draft 恢復契約

P0 沿用單一 active draft invariant。

### 沒有 current draft

- 直接顯示今日名單、QR Code 與收容編號搜尋。
- 不顯示空的恢復 card 或誤導性錯誤。

### 有可恢復 current draft

- 只有 `status=active`、尚未過期、organization 與目前 context 一致，且 animal 在今日授權名單內時可恢復。
- 提示至少顯示動物名稱、可用時顯示收容編號，以及轉為繁中文案的目前進度。
- 提供「繼續回報」與「稍後處理」。
- 「繼續回報」前往 `/care-report`；該頁重新向後端取得 current draft。
- 「稍後處理」只關閉本次提示並留在 `/animal-confirmation`，不得 cancel、delete 或修改 Draft。

### 不可恢復 current draft

- 過期、非 active、context 不一致或 animal 不在授權名單時，不顯示答案、動物詳細資訊或其他收容所資訊。
- 顯示安全的「目前無法恢復」與重試／聯絡管理者下一步。
- 不自動切換 Active Shelter Context。

多筆 active draft 選擇不屬於 P0；若未來改變既有 domain invariant，必須另行更新 spec、contract 與安全驗證。

## 8. Session、Context 與錯誤契約

| Condition | UI 結果 | Navigation／資料結果 |
| --- | --- | --- |
| 沒有 token | 安全 redirect status | 清除可用 cache，replace `/login`；children 不掛載 |
| profile/context 401 | Session 已失效繁中 status | 清除 auth，replace `/login`；受保護內容不可繼續查看 |
| context 缺少／409 | 不含資料的 context-required state | 提供返回登入／選擇、重試或聯絡管理者；不自動 loop |
| Membership/context 不一致 | 不含資料的安全限制 state | 不使用前一次 sessionStorage context；不載入 children |
| profile/context network／5xx | 可理解 error state | 提供重試、返回或重新登入；不得顯示 stale protected content |
| 志工開啟 management route | redirecting status | replace `/animal-confirmation`；management request 為 0 |

所有錯誤不得顯示受保護資料是否存在、資料筆數、動物／回報內容或其他收容所名稱。

## 9. Redirect 與 browser history 契約

- Login destination 與 role mismatch 使用 `replace`，避免 back 回到已完成登入頁或被拒 management route 後直接顯示舊內容。
- Redirect destination 與目前 pathname 相同時不得再次 redirect。
- Redirecting state 不掛載 children。
- Reload 與 browser back 必須重新執行 profile/context gate。
- 無 token、session 401、context-required、temporary error 與 role mismatch 的 flow 都必須在有限 state 終止；自動化測試不得觀察到連續 navigation loop。

## 10. 可及性與響應式契約

- Checking、redirecting、context-required 與 error 都有可理解的台灣繁體中文 title、description 與下一步。
- Loading／redirecting 使用適當的 polite status announcement；阻斷錯誤使用可讀取的 alert 語意，但不得重複播報。
- 「繼續回報」、「稍後處理」、「重試」、「返回登入」等控制可用鍵盤操作且有可見 focus。
- 360px 寬度下，status、draft prompt、長中文錯誤與主要操作不得重疊、被截斷或造成非必要水平捲動。
- 必要資訊不可只靠 color、icon 或 animation 表達；reduced motion 不影響流程理解。

## 11. 驗收證據契約

P0 至少留下：

- 4 個角色的 login destination matrix。
- 志工對全部 management route pattern 的 deep link、reload 與 back 結果。
- 志工 management request count = 0 的 network assertion。
- 工作人員、收容所管理者與平台管理員的 `/` regression。
- 無 draft、可恢復 draft、過期／不可恢復 draft、save failure 的結果。
- Session 401、context 缺少與 temporary error 的終止 state。
- 360／768／1024／1440 viewport、keyboard、axe 與 reviewer-approved visual evidence。
- 既有後端 authorization、tenant isolation、OpenAPI、CRM、LINE 與 AI regression 結果。

Browser mock 只證明 UI contract；不得取代真實後端 security／isolation tests。
