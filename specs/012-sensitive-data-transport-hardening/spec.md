# Feature Specification: 敏感資料傳輸與紀錄防護

**Feature Branch**: `012-sensitive-data-transport-hardening`

**Created**: 2026-09-04

**Status**: Draft

**Input**: User description: "檢視整個專案，規劃解決帳號密碼或其他敏感資料出現在網址列、歷史、代理與存取紀錄中的同類資安問題。"

## User Scenarios & Testing

### User Story 1 - 登入資訊不進入網址 (Priority: P1)

管理者、工作人員或志工以帳號密碼登入時，即使頁面尚未完成載入、前端功能失效、重複提交或操作過快，帳號密碼都不會出現在網址列、瀏覽器歷史、書籤或分享連結中。

**Why this priority**: 密碼一旦進入 URL，會跨越瀏覽器、代理、監控與外部 tunnel 等多個保存邊界，無法靠單一後端遮罩完整補救。

**Independent Test**: 在正常載入、腳本停用、腳本載入延遲及提交失敗情境下完成或嘗試登入，檢查所有可見 URL、歷史與請求目標均不含帳號密碼。

**Acceptance Scenarios**:

1. **Given** 登入頁正常可用，**When** 使用者提交帳號密碼，**Then** 登入資料只經核准的請求內容傳送，頁面 URL 維持乾淨。
2. **Given** 登入頁尚未完成互動功能掛載，**When** 使用者嘗試提交，**Then** 系統不得以查詢參數傳送任何登入欄位。
3. **Given** 使用者開啟含歷史遺留敏感參數的登入 URL，**When** 頁面處理請求，**Then** 不使用該參數登入，並導向不含敏感參數的標準 URL。

---

### User Story 2 - 全系統敏感 URL 有明確政策 (Priority: P1)

安全審查者可以區分「禁止放入 URL 的秘密」、「經核准且受限制的短效 capability」、「必要但需最小化的流程參考值」與「一般查詢條件」，並能追溯每個例外的目的、期限、綁定範圍與記錄政策。

**Why this priority**: StrayHub 同時有登入、LINE、LIFF、QR、圖片 capability、下載連結與管理查詢，若只修正 password，其他 credential 仍可能透過同一設計缺口外洩。

**Independent Test**: 對所有前端路由、API 契約、QR／LINE 深連結與下載連結執行敏感參數盤點，確認每個敏感參數不是被禁止，就是列入具備補償控制的核准例外。

**Acceptance Scenarios**:

1. **Given** 新增一個可能攜帶 token、secret、password、identity 或 entry reference 的 URL，**When** 執行安全檢查，**Then** 未登錄的敏感參數會使驗證失敗。
2. **Given** 核准的短效 capability 必須出現在 URL，**When** 使用者或外部服務取用，**Then** capability 具有限時、用途、租戶、資源綁定且不會被紀錄原值。
3. **Given** 一般搜尋、分頁或日期查詢，**When** 套用安全政策，**Then** 不會因過度遮罩而破壞必要的診斷與產品功能。

---

### User Story 3 - 所有記錄層不保存 credential (Priority: P1)

維運人員可以使用瀏覽器、外部 tunnel、反向代理、Web runtime、API runtime 與應用程式記錄診斷問題，但這些記錄不得永久保存密碼、access token、refresh token、LINE ID token、簽名 URL、capability 原值或受保護身分識別值。

**Why this priority**: 同一請求會經過多層系統；只在 FastAPI 遮罩無法保護 nginx、Next.js 或 ngrok 已收到的完整 URL。

**Independent Test**: 使用唯一 sentinel 值走過登入、LINE／LIFF、QR、圖片與下載流程，集中檢查各層記錄，確認 sentinel 不存在且非敏感診斷欄位仍保留。

**Acceptance Scenarios**:

1. **Given** 敏感值位於請求內容、header、URL 或結構化欄位，**When** 任一層產生記錄，**Then** 記錄只保留遮罩值或不含 query 的路徑。
2. **Given** 敏感 URL 被當成 Referer 傳入，**When** 產生 access log，**Then** 不保存敏感 Referer 原文。
3. **Given** 發生錯誤或例外，**When** 系統記錄錯誤，**Then** exception、payload 與 context 不會繞過相同遮罩政策。

---

### User Story 4 - 公開 demo tunnel 採最小暴露 (Priority: P2)

開發者使用 ngrok 執行 LINE／LIFF demo 時，只公開該 demo 必要的路徑；管理登入與後台不會因同一 tunnel 自動暴露。若確實需要遠端展示管理功能，必須以明確選項、短效帳密與純 synthetic data 啟用。

**Why this priority**: `local-only` 帳密在公開 tunnel 存續期間並非真正只限本機，固定預填密碼會把方便性轉化為遠端可利用的入口。

**Independent Test**: 啟動預設 LINE demo tunnel，驗證必要的 webhook／LIFF 路徑可用，登入與管理路徑被拒絕；再以明確 opt-in 驗證受控展示模式。

**Acceptance Scenarios**:

1. **Given** 使用預設 LINE demo 模式，**When** 外部來源要求管理登入或後台路徑，**Then** 系統拒絕且不洩漏帳號狀態。
2. **Given** 開發者明確啟用遠端管理展示，**When** tunnel 啟動，**Then** 系統要求短效 credential、synthetic data 與醒目的暴露提示。
3. **Given** tunnel 結束，**When** 開發者再次啟動，**Then** 不沿用上次的短效 credential 或敏感檢查紀錄。

**Implementation disposition (2026-09-04)**: 產品 owner 尚未提出遠端 management demo
需求，因此本 feature 採 `NOT IMPLEMENTED — local-only management`。Acceptance Scenario 2／3
不建立隱含例外；若未來確有需求，必須另立獨立 deployment/profile 規格與 owner 審核，不得擴張
LINE／LIFF allowlist。

---

### User Story 5 - 變更前即可阻止回歸 (Priority: P2)

開發者新增表單、redirect、QR、LINE Flex、LIFF callback、signed URL 或 logging 欄位時，可以在本機與 CI 得到具體失敗原因，避免敏感資料回到 URL 或 log。

**Why this priority**: 此類問題跨多層且人工審查容易遺漏，需要可重複的契約與 runtime evidence。

**Independent Test**: 注入禁止的 URL 參數與未遮罩 sentinel，確認安全測試會失敗；修正後確認合法 query 與核准 capability 仍可運作。

**Acceptance Scenarios**:

1. **Given** 表單可能退化為帶密碼的 GET，**When** 執行驗證，**Then** 測試明確指出違反安全提交政策。
2. **Given** 新增未登錄的敏感 query key，**When** 執行驗證，**Then** CI 拒絕變更並指出需要移出 URL 或登錄例外。
3. **Given** 合法 query 與核准例外，**When** 執行回歸測試，**Then** 原有功能、租戶隔離與診斷能力保持正常。

### Edge Cases

- 使用者在首次載入、慢速網路或前端腳本錯誤時按下 Enter。
- 密碼管理器、自動填入或瀏覽器恢復表單狀態後觸發原生提交。
- 敏感參數大小寫、重複出現、URL encoding、fragment 或巢狀 signed URL。
- HTTP 轉 HTTPS redirect 收到已帶敏感 query 的請求。
- 外部身分服務 callback 必須使用標準 `code`／`state` 時的例外與清理。
- QR 或 LINE Flex 中的 capability 被截圖、轉傳、重播或跨收容所使用。
- 錯誤訊息、exception repr、結構化 audit context 或測試 artifact 意外包含完整值。
- access log 已遮罩但 Referer、ngrok inspector、瀏覽器 HAR 或 screenshot 仍保留秘密。
- 非敏感的搜尋、日期、分頁與 cache version query 被誤判為秘密。

## Requirements

### Functional Requirements

- **FR-001**: 系統 MUST 建立單一敏感資料分類與 URL 使用政策，涵蓋 password、session credential、provider token、signed URL、capability、外部身分識別與流程參考值。
- **FR-002**: Password、access token、refresh token、LINE ID token、Authorization credential 與長效 secret MUST NOT 出現在 URL、fragment、redirect destination、QR payload 或可分享連結。
- **FR-003**: 所有登入表單 MUST 在互動功能尚未掛載或失效時仍避免使用 GET 傳送登入欄位。
- **FR-004**: 管理登入頁 MUST NOT 預填密碼；公開 tunnel 模式不得預設提供可直接使用的固定管理 credential。
- **FR-005**: 含歷史遺留禁止參數的 URL MUST 不採信其 credential，並以安全方式回到標準 URL。
- **FR-006**: 每個允許存在於 URL 的敏感值 MUST 有文件化的 purpose、最長 lifetime、租戶／組織綁定、資源綁定、重播政策、清除時點與 log 行為。
- **FR-007**: QR token、entry reference、圖片 capability、signed download 與標準身分 callback 參數 MUST 分別接受風險審查，不得因名稱都叫 token 而共用同一授權政策。
- **FR-008**: 所有 shelter-owned capability MUST 在伺服器端重新驗證 organization 與資源歸屬，不得信任 client 提供的 shelter identifier。
- **FR-009**: 瀏覽器、外部 tunnel、反向代理、Web runtime、API runtime、應用程式與錯誤記錄 MUST 遵循一致的敏感值遮罩結果。
- **FR-010**: 對無法可靠局部遮罩的 access log，系統 MUST 使用不含 query 與敏感 Referer 的最小記錄格式，同時保留 method、path、status、size、latency 與 correlation 所需資訊。
- **FR-011**: 系統 MUST 保留合法搜尋、分頁、日期、排序及公開 cache version 等非敏感 query 的既有功能。
- **FR-012**: 預設 LINE／LIFF tunnel MUST 只公開實際需要的路徑，管理登入與管理後台必須維持本機或被明確拒絕。
- **FR-013**: 遠端管理 demo 若被明確啟用，MUST 限定 synthetic data、短效 credential、清楚的風險提示與結束後失效流程。
- **FR-014**: 安全測試 MUST 使用唯一 sentinel 驗證每一層記錄沒有原始 credential，且測試輸出本身不得洩漏真實秘密。
- **FR-015**: 專案 MUST 有可機器檢查的敏感 URL 例外清單；未登錄例外不得通過驗證。
- **FR-016**: 系統 MUST 對正常、腳本未掛載、失敗、redirect、callback、過期、重播及跨租戶情境提供回歸驗證。
- **FR-017**: 已知外洩事件 MUST 有停止暴露、輪替 credential、清理可控記錄與記載不可回收副本風險的處理程序。
- **FR-018**: 本功能 MUST 不降低 LINE webhook 簽章驗證、登入驗證、角色授權、tenant isolation、RLS 或既有 capability policy。
- **FR-019**: 本功能 MUST 不把敏感完整值寫入 audit log；安全事件只記錄類型、結果、時間、租戶範圍與不可逆識別資訊。
- **FR-020**: 所有安全例外 MUST 有 owner、理由、驗證方式與複查條件；未指定任意永久例外。

### Key Entities

- **Sensitive Data Class**: 敏感值類型、允許的傳輸位置、記錄政策與處置等級。
- **URL Exception**: 必須位於 URL 的受控值，其 purpose、lifetime、scope、清理與複查條件。
- **Exposure Surface**: 瀏覽器、tunnel、proxy、runtime、application、audit 與測試 artifact 等可能保存資料的邊界。
- **Security Regression Evidence**: 以 synthetic sentinel 產生的可重複驗證結果，不包含真實 credential。
- **Demo Exposure Mode**: 本機、預設公開 LINE／LIFF、明確遠端管理展示三種暴露範圍與生命週期。

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% 登入驗收情境的網址列、歷史與請求目標不包含 username 或 password。
- **SC-002**: 專案中所有敏感 URL 使用點皆完成分類，未登錄敏感參數數量為 0。
- **SC-003**: 使用 sentinel 跑過所有代表性流程後，受檢記錄與 artifact 中的原始敏感值出現次數為 0。
- **SC-004**: 100% 核准 URL 例外具有 purpose、lifetime、scope、清理時點與 log policy。
- **SC-005**: 預設公開 demo tunnel 對管理登入與管理頁面的外部存取成功率為 0%，必要 LINE／LIFF 流程成功率維持 100%。
- **SC-006**: 既有合法搜尋、分頁、日期與 cache version query 的代表性回歸情境全部通過。
- **SC-007**: 跨收容所重播所有 shelter-owned capability 的代表性測試均被拒絕，且不洩漏資源存在性。
- **SC-008**: 新增一個未登錄敏感 URL 參數時，CI 能在同一驗證流程中明確失敗。
- **SC-009**: 維運人員仍能從去敏後記錄判斷 method、path、status、latency 與 correlation，代表性故障定位任務成功率為 100%。
- **SC-010**: 已知 credential URL 事件的停止暴露、輪替與可控記錄處理可在 30 分鐘內依 runbook 完成。

## Assumptions

- 本功能優先處理 credential 經 URL 與 logging surface 外洩，不重建整套 authentication 或 session storage 架構。
- 現有登入、LINE／LIFF、QR、媒體 capability 與多收容所授權模型繼續沿用，僅收斂傳輸與記錄邊界。
- `entry`、`qr_token`、圖片 capability、OAuth／LIFF callback 參數可能有必要的 URL 使用情境，但必須逐項審查，不預設全部禁止。
- ngrok 或同類第三方 tunnel 無法在收到請求後回收已看見的 URL，因此以源頭不產生禁止 query 與最小公開路由為主要控制。
- 正式資料與 synthetic demo data 必須分離；公開 demo 不因資料為 synthetic 就免除 credential 與路由最小化要求。
- 本階段產出設計與驗證規劃，不直接輪替 credential、不刪除 log，也不修改 production infrastructure。
