# Feature Specification: 毛孩日記管理頁

**Feature Branch**: `[011-growth-diary-management]`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "管理後台實作毛孩日記頁面"

## User Scenarios & Testing _(mandatory)_

### User Story 1 - 查看所屬收容所的毛孩日記 (Priority: P1)

收容所工作人員或管理員可以從管理後台導覽進入毛孩日記頁面，查看目前收容所領養人提交的日記，快速掌握動物名稱、提交時間、照片或文字內容，以及 AI 產生的情緒與摘要。

**Why this priority**: 後端已保存毛孩日記，但目前沒有管理介面；先讓授權人員能看見原始內容與摘要，才能實際進行領養後追蹤。

**Independent Test**: 在一個收容所有數筆文字、照片及尚未完成 AI 分析的日記時，以該收容所工作人員登入並開啟毛孩日記頁，即可辨識每筆日記的動物、原始內容、時間與分析狀態。

**Acceptance Scenarios**:

1. **Given** `STAFF`、`SHELTER_ADMIN` 或具有 active shelter context 的 `PLATFORM_ADMIN` 已登入並選定收容所，**When** 從管理導覽進入毛孩日記，**Then** 系統依最新到最舊顯示該收容所的日記。
2. **Given** 日記包含照片，**When** 頁面載入完成，**Then** 使用者可看到照片預覽，且照片載入失敗時仍可閱讀其他內容。
3. **Given** 日記包含領養人原始文字，**When** 使用者查看該筆日記，**Then** 原始文字與 AI 摘要分開呈現，不會把衍生內容誤認為領養人原話。
4. **Given** 日記尚未產生 AI 分析或分析失敗，**When** 使用者查看該筆日記，**Then** 系統顯示「等待分析」或「尚無分析」，且原始內容仍正常可見。
5. **Given** 目前收容所沒有任何日記，**When** 頁面載入完成，**Then** 顯示清楚的空狀態與日記來源說明，而不是空白頁面。
6. **Given** 日記包含 AI 衍生內容，**When** 使用者查看分析區塊，**Then** 系統明確標示內容由 AI 產生、不是醫療診斷，並在可取得時呈現模型與分析時間等來源資訊。
7. **Given** 授權使用者展開一筆日記的 AI 來源資訊，**When** detail 載入完成，**Then** 可查看 raw output 與完整 provenance；清單本身不包含 raw output。

---

### User Story 2 - 快速找出需要關注的日記 (Priority: P2)

工作人員可以依關注狀態篩選日記，並以動物名稱或收容編號搜尋，以便從大量更新中優先查看 AI 標示為需要注意的紀錄。

**Why this priority**: 毛孩日記的工作價值在於領養後追蹤；提供基本搜尋與情緒篩選，可降低找出異常紀錄所需時間，但不影響 P1 的基本可見性。

**Independent Test**: 準備包含 `concern`、一般情緒及未分析狀態的日記，以情緒篩選及動物關鍵字搜尋，確認結果數量與內容正確，清除條件後恢復完整清單。

**Acceptance Scenarios**:

1. **Given** 清單包含不同 AI 情緒的日記，**When** 使用者選擇「需要關注」，**Then** 只顯示目前收容所中被標示為需要關注的日記。
2. **Given** 清單包含多隻動物，**When** 使用者輸入動物名稱或收容編號，**Then** 顯示符合關鍵字的日記並清楚呈現結果數量。
3. **Given** 使用者套用的條件沒有符合資料，**When** 篩選完成，**Then** 顯示無符合結果的狀態並提供清除條件的方法。

---

### User Story 3 - 在不同裝置安全閱讀日記 (Priority: P3)

工作人員可在桌面、平板與手機瀏覽毛孩日記，並透過鍵盤操作導覽、篩選及閱讀內容；載入或授權失敗時能理解原因並重試或返回安全頁面。

**Why this priority**: 收容所人員可能使用不同裝置處理追蹤工作，基本響應式與無障礙支援可避免資訊只在特定裝置可用。

**Independent Test**: 以桌面、平板與手機寬度開啟頁面，使用鍵盤操作搜尋與篩選，並模擬 API 失敗及權限不足，確認沒有水平溢出且回饋可理解。

**Acceptance Scenarios**:

1. **Given** 使用者以手機寬度開啟頁面，**When** 瀏覽包含長文字及照片的日記，**Then** 內容不被裁切、沒有水平捲動，主要資訊仍可辨識。
2. **Given** 日記載入失敗，**When** 頁面顯示錯誤，**Then** 使用者可看到不洩漏內部資訊的說明並重新嘗試。
3. **Given** 使用者沒有工作人員或收容所管理員權限，**When** 嘗試直接開啟頁面，**Then** 系統拒絕顯示日記內容，且不洩漏其他收容所是否有資料。

### Edge Cases

- 同一動物可以有多筆日記，每筆必須保留並依提交時間獨立顯示，不得互相覆蓋。
- 日記可能只有照片或只有文字；兩者都沒有的異常資料應顯示安全的缺少內容狀態，不使整頁失敗。
- authenticated photo endpoint 可能因 legacy MIME 不可信、物件不存在或儲存服務暫時失敗；頁面必須保留文字、時間及摘要並提供圖片替代狀態。
- AI 情緒、回覆或工作人員摘要皆可能為空；缺少衍生內容不得隱藏原始日記。
- 既有日記可能早於 AI 來源資訊保存機制；頁面應標示「來源資訊未留存」，不得用目前設定值偽裝成當時實際使用的模型或版本。
- 長文字、特殊字元、換行與表情符號不得破壞版面，也不得被當成可執行內容。
- 切換收容所或重新登入後，頁面不得保留前一收容所的日記、搜尋結果或快取內容。
- 收容所 A 的工作人員不得透過網址、搜尋、篩選或請求參數看到收容所 B 的日記。
- 空清單與套用篩選後無結果必須使用不同訊息，避免誤判系統沒有任何日記。
- 新上傳照片可能是 JPEG、PNG、WebP、具有 EXIF orientation、透明背景或動畫；系統只保存安全正規化後的單幀 WebP，不保存原始或中間檔。
- 小型壓縮檔仍可能具有超大解析度；系統必須在完整解碼前依尺寸拒絕超過 25,000,000 pixels 的圖片。
- 圖片正規化、物件儲存或資料庫建立任一步驟失敗時，不得建立不完整日記；若物件已寫入但資料庫 transaction 失敗，必須嘗試刪除新物件且不可靜默忽略清理失敗。

## Requirements _(mandatory)_

### Functional Requirements

- **FR-001**: 管理後台 MUST 提供可由既有管理導覽進入的「毛孩日記」頁面。
- **FR-002**: 頁面與相關 list/detail/photo API MUST 僅供經後端驗證的 `STAFF`、`SHELTER_ADMIN`，以及具有 active shelter context 的 `PLATFORM_ADMIN` 存取；`VOLUNTEER`、沒有 active shelter context 的使用者及其他收容所使用者不得存取，前端隱藏導覽不得作為唯一授權控制。
- **FR-003**: 系統 MUST 只回傳目前已授權收容所的毛孩日記，且不得信任使用者自行提供的收容所識別來擴大範圍。
- **FR-004**: 頁面 MUST 依提交時間由新到舊顯示日記，並為每筆呈現動物名稱、收容編號、提交時間、原始文字及照片可用狀態。
- **FR-005**: 頁面 MUST 將領養人原始內容與 AI 衍生的情緒、領養人回覆及工作人員摘要清楚分區與標示。
- **FR-006**: AI 分析尚未完成、失敗或沒有設定時，頁面 MUST 保留原始內容並顯示不誤導的分析狀態。
- **FR-007**: 使用者 MUST 能依 AI 情緒篩選目前收容所的完整日記範圍，至少包含全部、需要關注、一般、正向及尚未分析等可理解分類。
- **FR-008**: 使用者 MUST 能以動物名稱或收容編號搜尋目前收容所的日記，搜尋文字前後空白及大小寫差異不得造成不合理落差。
- **FR-009**: 頁面 MUST 區分初次載入、成功、有資料、真正空清單、篩選無結果、錯誤及重新載入等狀態。
- **FR-010**: 照片 MUST 透過 authenticated、same-origin、active-organization-scoped endpoint 顯示；不得暴露 object key、object storage hostname 或 query-string Bearer token，圖片失敗時不得導致日記其他內容消失。
- **FR-011**: 頁面 MUST 在桌面、平板與手機寬度可閱讀，長文字與照片不得造成水平溢出，互動控制須支援鍵盤操作及可辨識焦點。
- **FR-012**: 頁面 MUST 使用台灣正體中文呈現主要介面文字、時間及情緒標籤，並使用既有管理後台視覺與元件模式。
- **FR-013**: API 回應與前端型別 MUST 明確定義日記欄位的必填、可空與時間格式，避免以未驗證的任意物件直接渲染。
- **FR-014**: 本功能 MUST 為唯讀管理頁；第一版不允許工作人員編輯、刪除、覆寫領養人原文或直接改寫 AI 分析。
- **FR-015**: 切換收容所、登出或授權失效時，頁面 MUST 清除或隔離前一個收容所的日記資料，不得短暫顯示跨收容所內容。
- **FR-016**: AI 衍生內容 MUST 明確標示為未經人工確認的輔助資訊，不得宣稱醫療診斷、健康正常或正式處理結論；系統 MUST 保留並在授權介面提供可用的模型、提示版本、分析時間與原始輸出追溯資訊，既有缺少來源資訊的紀錄須誠實標示。
- **FR-017**: 新照片 MUST 接受實際格式與 declared MIME 相符的 JPEG、PNG 或 WebP，原始 compressed input 上限為 10 MB；系統 MUST 在完整 decode 前拒絕寬乘高超過 25,000,000 pixels 的圖片，不得只以 byte size 作為安全邊界。
- **FR-018**: 新照片 MUST 先套用 EXIF orientation，再移除 EXIF 與其他 metadata；animated input 只處理第一 frame，透明圖片保留 alpha channel，且不得放大小於目標尺寸的圖片。
- **FR-019**: 新照片 MUST 依序嘗試正規化為長邊不超過 1600 px、quality 82 的 WebP；若超過 2 MB，依序重試 quality 72，以及長邊不超過 1280 px、quality 68；最終仍超過 2 MB MUST 拒絕。
- **FR-020**: 成功處理的新照片 MUST 只保存最終 WebP，且 MIME、size、checksum 均由最終 bytes 計算；不得保存原始檔、EXIF 版本或中間壓縮檔。
- **FR-021**: 圖片 sanitization 或 storage 失敗 MUST 不建立日記；storage 成功但資料庫 transaction 失敗時 MUST 執行 organization-scoped delete compensation，且不得送出「已記錄」成功回覆或註冊該 entry 的 AI task。cleanup failure MUST 產生可觀測錯誤紀錄，但不得向使用者暴露 object key 或內部例外。
- **FR-022**: 新資料有 `photo_key` 時，`photo_content_type` MUST 為 `image/webp`；legacy record 可為 null，無法可信判斷 MIME 時 photo endpoint MUST fail closed。成功 photo response MUST 為 `image/webp`，並帶有 `Cache-Control: private, no-store` 與 `X-Content-Type-Options: nosniff`。
- **FR-023**: 第一版 MUST NOT 為 diary list/detail、photo 或 AI raw output read 新增 audit event；此決策不影響 authentication、authorization、錯誤 log 或既有 mutation audit。

### Key Entities _(include if feature involves data)_

- **毛孩日記紀錄**：領養人針對單一領養詢問與動物提交的一次更新，包含原始文字、照片參照、提交時間及可空的 AI 衍生欄位。
- **動物摘要**：用於辨識日記所屬動物的名稱與收容編號；必須與日記的收容所範圍一致。
- **AI 分析狀態與來源**：由情緒、領養人回覆、工作人員摘要及模型、提示版本、分析時間與原始輸出追溯資訊組成的衍生資料，不取代原始日記，也不代表醫療診斷或正式處理結論。
- **管理者的收容所範圍**：由登入身分與 Membership 決定的單一管理資料邊界，控制日記清單與照片存取。

## Success Criteria _(mandatory)_

### Measurable Outcomes

- **SC-001**: 有權限的工作人員可在進入頁面後 3 秒內看到首批日記或明確的空狀態／錯誤狀態。
- **SC-002**: 標準測試資料中，100% 的日記都能正確顯示動物識別、提交時間及至少一種原始內容狀態，AI 欄位缺失不影響原始內容可見性。
- **SC-003**: 在跨收容所授權測試中，工作人員可見其他收容所日記的比例為 0%，直接請求及切換收容所後的暫存畫面亦不得洩漏。
- **SC-004**: 使用包含至少 50 筆日記的標準資料時，工作人員可在 15 秒內透過搜尋或情緒篩選找到指定動物或所有需要關注的紀錄。
- **SC-005**: 桌面、平板與手機寬度的驗收案例中，100% 沒有水平溢出、內容遮蔽或無法使用鍵盤操作的主要控制項。
- **SC-006**: API、圖片或 AI 衍生資料失敗的驗收案例中，100% 提供可理解的降級狀態，且不把錯誤詳情、憑證或其他收容所資訊顯示給使用者。
- **SC-007**: 新產生的 AI 分析紀錄有 100% 可追溯至模型、提示版本、分析時間及原始輸出；既有缺少來源資料的紀錄有 100% 被標示為來源資訊未留存，且所有 AI 區塊均顯示未經人工確認提示。
- **SC-008**: 所有成功保存的新日記照片皆為不超過 2 MB、長邊不超過 1600 px、無 EXIF 的單幀 WebP；被拒絕的照片不留下 object 或日記，storage 後發生的資料庫失敗會執行補償刪除，補償失敗則有 100% 可觀測的錯誤紀錄。

## Assumptions

- 第一版以查看與追蹤為主，不新增編輯、刪除、人工覆核、狀態處理或聯絡領養人的工作流程。
- 沿用既有登入、收容所切換、工作人員／管理員權限與管理後台導覽，不建立另一套身分或權限系統。
- 沿用既有毛孩日記資料與管理清單能力；若介面契約需要補強型別、分頁或查詢參數，可在不改變原始資料語意的前提下擴充。
- 搜尋與情緒篩選涵蓋目前收容所的日記並支援分頁；第一版不要求全文索引、領養人個資搜尋或跨收容所搜尋。
- 時間依管理後台既有台灣時區顯示規則呈現，資料來源時間不被覆寫。
- AI 分析是可選衍生資訊；沒有 Gemini 憑證或分析失敗時，毛孩日記管理頁仍須可用。
- 第一版沿用既有 buffered object read；2 MB final output ceiling 使本 feature 不需要新增 streaming storage abstraction。
- 所有三種允許的管理角色均可查看 detail 中的 AI raw output；raw output 不出現在 list。
- 第一版不為高頻 read request 新增 audit event；權限、tenant scope 與安全錯誤處理仍由後端強制。
