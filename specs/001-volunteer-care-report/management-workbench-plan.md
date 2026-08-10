# 管理工作台整體規劃

**狀態**：設計基線，尚未進入下一輪 UI 實作

**目的**：將登入、收容所 Context、動物、照護回報、Timeline、觀察語彙、帳號與 AI
覆核整合成一個依角色顯示的管理工作台。所有功能先遵循同一個 App Shell、導航、權限
與資料查詢邊界，再分階段交付模組，避免逐頁增加造成路由、Session、Context 與操作
流程不一致。

## 1. 產品決策

1. `/` 是管理工作台首頁，不再直接跳到某一隻動物的 Timeline。首頁提供今日摘要與
   主要任務入口；Timeline 是從動物清單、搜尋結果、首頁待辦或深層連結進入的工作頁。
2. `ORG-A` 只作本機 Seed 的預設展示 Context，不得寫死為正式產品行為。登入後應顯示
   帳號可用的收容所，使用者明確選擇目前 Context；若只有一個可用收容所，可以在畫面
   明確顯示並完成選定。
3. 前端只負責呈現與流程協調；Session、Membership、Role、Organization Scope、
   Animal、Report、Photo、AI 結果與 Audit 都由 FastAPI／CRM 作為唯一事實來源。
4. 角色沒有權限的模組不顯示在導航中；即使使用者直接輸入網址，後端仍必須重新驗證
   並回傳一致的拒絕結果。隱藏導航不是安全控制。
5. 志工的手機回報流程與工作人員管理工作台共用 CRM 與 Authentication，但保留獨立的
   mobile-first 入口；不把志工需要的逐題回報塞進桌面管理側欄。

## 2. 主要使用流程

### 工作人員日常流程

```text
登入
  → 選擇／確認 Active Shelter Context
  → 管理工作台首頁
  → 動物清單或收容編號搜尋
  → 動物檔案
  → 近期 Timeline
  → 展開單日／單筆回報
  → 查看原始資料、照片、AI 狀態與人工修正
```

### 收容所管理員流程

```text
登入 → Context → 工作台
  → 動物與收容資料
  → 帳號與 Membership
  → Cage／Area／QR Code
  → 今日可回報範圍
  → 觀察語彙
  → 回報／AI 覆核與稽核紀錄
```

### 平台管理員流程

```text
登入 → 平台工作台
  → 收容所總覽
  → 建立／啟用／停用收容所
  → 初始管理員與服務狀態
  → 選定目標收容所後進入該租戶工作台
  → 所有跨機構操作留下 Audit Record
```

### 志工流程

```text
LINE Rich Menu／LIFF
  → 明確選擇 Active Shelter Context
  → 今日可回報動物／QR／收容編號搜尋
  → 動物確認卡
  → Server-side Draft
  → 結構化回報
  → 摘要確認與送出
```

## 3. 共通 App Shell

所有 `(management)` 路由使用同一個 Layout，不由各頁自行重複實作登入或 Token 邏輯。

```text
ManagementLayout
├── AppHeader
│   ├── 品牌與目前工作區
│   ├── Active Shelter Context 選擇器
│   ├── 目前角色／帳號
│   └── 登出
├── AppSidebar（依角色產生）
├── Breadcrumbs／頁面標題／主要操作
├── StatusBanner（權限、Context、網路與同步狀態）
└── MainContent
```

共通行為：

- `AuthProvider` 在 Client 端維持目前 Session、使用者、Membership 與 Active Context 的
  顯示狀態；正式授權仍由 FastAPI 判定。
- `apiFetch` 統一加入 Bearer Token、處理 401／409 Context required、Refresh 與登出。
- Context 切換後清除舊租戶查詢快取，重新載入目前頁面的 CRM 資料；不得保留舊租戶的
  動物、回報、照片或選項在畫面上。
- Header 永遠顯示目前收容所代碼與名稱；平台級操作顯示 `PLATFORM`，進入特定收容所
  工作區後顯示該收容所。
- 所有 loading、empty、error、forbidden、stale Context 與 offline 狀態使用共通元件。

## 4. 路由與模組邊界

| 路由                            | 主要角色                   | 目的                                 | 依賴的 CRM 能力                        |
| ------------------------------- | -------------------------- | ------------------------------------ | -------------------------------------- |
| `/login`                        | 全部                       | 登入、Refresh、選定 Context          | Authentication、Membership             |
| `/`                             | 平台／管理員／工作人員     | 今日摘要、待處理任務、快速入口       | Dashboard aggregation                  |
| `/animals`                      | 平台／管理員／工作人員     | 動物清單、搜尋、篩選與最近活動       | Animal list/search、Scope              |
| `/animals/:animalId`            | 平台／管理員／工作人員     | 動物檔案、基本資料、QR／區域摘要     | Animal detail、Cage／Area              |
| `/animals/:animalId/timeline`   | 平台／管理員／工作人員     | 近 14 日與更早歷程                   | Timeline、Report、Media、AI            |
| `/reports`                      | 管理員／工作人員           | 回報收件匣、狀態篩選、待覆核         | Report list/detail、Archive/Correction |
| `/reports/:reportId`            | 管理員／工作人員           | 原始回報、照片、AI 與人工修正        | Report、Media、AI、Audit               |
| `/settings/observation-options` | 管理員／工作人員           | 觀察類別與有效選項維護               | Effective Vocabulary                   |
| `/shelters`                     | 平台／收容所管理員         | 收容所、帳號、Membership、Cage／Area | Organization management                |
| `/settings/reportable-scope`    | 管理員／授權工作人員       | 個別動物、區域、指定志工範圍         | Daily Reportable Scope                 |
| `/settings/qr-codes`            | 管理員／授權工作人員       | QR 建立、撤銷、重新產生與列印資料    | QR Code management                     |
| `/settings/audit`               | 平台／管理員／授權工作人員 | 依權限查看異動追蹤                   | Audit query                            |
| `/animal-confirmation`          | 志工                       | 手機動物確認與建立回報 Draft         | Animal selection、Draft                |
| `/care-report`                  | 志工                       | LIFF／備援回報與 Draft 恢復          | Draft、Report                          |

既有 `/shelters`、`/settings/observation-options` 與 Timeline 頁面先納入 Shell；不再以
獨立頁面各自建立一套 Header、登入檢查或 API client。

## 5. 角色導航矩陣

| 模組                     | PLATFORM_ADMIN | SHELTER_ADMIN |  STAFF |      VOLUNTEER |
| ------------------------ | -------------: | ------------: | -----: | -------------: |
| 工作台首頁               |              ✓ |             ✓ |      ✓ |    mobile 入口 |
| 動物清單／檔案／Timeline |              ✓ |             ✓ |      ✓ |      ✗完整歷程 |
| 回報收件匣／修正／封存   |              ✓ |             ✓ | 依授權 |              ✗ |
| 觀察語彙                 |              ✓ |             ✓ |      ✓ | 只使用有效選項 |
| 帳號／Membership         |              ✓ |  所屬 Shelter |      ✗ |              ✗ |
| 收容所建立／啟用／停用   |              ✓ |             ✗ |      ✗ |              ✗ |
| Cage／Area／QR           |              ✓ |  所屬 Shelter | 依授權 |   只掃描／解析 |
| Daily Reportable Scope   |              ✓ |             ✓ | 依授權 |              ✗ |
| AI 人工覆核              |              ✓ |             ✓ | 依授權 |              ✗ |
| Audit 查詢               |              ✓ |  所屬 Shelter | 依授權 |              ✗ |

角色矩陣只控制導航與使用者體驗；每個 API 仍必須以已驗證 Session、Membership、Role
與 Organization Scope 重驗證。

## 6. API／資料缺口，先於 UI 補齊

目前已存在登入、Context、動物候選、Timeline、觀察選項、Organization 管理、Draft、
Report detail、Media 與部分 AI API。要支撐完整工作台，需先盤點並補足以下契約：

1. **Dashboard summary**：依目前 Scope 回傳今日可回報動物數、最近回報、待處理 AI、
   未完成 Draft 或異常提醒；只回傳角色可見摘要。
2. **Management animal list/detail**：區分「志工可回報候選」與「工作人員管理清單」，
   支援名稱、收容編號、Cage／Area、狀態與 Scope 篩選，不能把完整名冊誤用成志工名單。
3. **Report inbox/detail**：列出回報、依日期／動物／狀態篩選、取得原始內容、修正與
   Archive；正式回報不得 Hard Delete。
4. **Reportable Scope**：個別動物、Cage／Area、指定志工的建立、修改、停用與重新驗證。
5. **Animal／Cage／Area／QR management**：動物檔案維護、收容編號異常、QR 建立／撤銷；
   QR 只作候選查詢，不成為授權憑證。
6. **AI review queue**：依 Job／Observation 狀態列出待處理、失敗、無效與已覆核項目；
   人工決定保留原始 AI 輸出與 Audit。
7. **Audit query**：只讀、依 Scope／操作者／資源／時間查詢，禁止修改或刪除。

上述是 UI 對應的 API 缺口清單；在契約補齊前不以前端拼接多個低階 endpoint 冒充完整
工作台，也不在 Next.js 保存正式 CRM 副本。

## 7. 交付階段與 Gate

### Phase A：Shell 與身分邊界

- 共通 Layout、Header、Sidebar、Breadcrumb、Error／Empty 狀態。
- Login、Refresh、Logout、Context 選擇器、401／409 導向。
- `/` 工作台首頁骨架與角色導覽矩陣。
- Gate：A／B Context 切換後畫面與 API 資料不交叉；直接輸入受限網址仍由後端拒絕。

### Phase B：動物工作流

- 動物清單／搜尋／篩選、動物檔案與 Timeline 串成完整三步流程。
- 首頁快速入口導向清單、指定動物或待處理回報，不再硬編碼第一隻 Animal。
- Gate：工作人員最多三次主要操作進入指定 Timeline；近 14 日、同日多筆、無回報與
  AI 失敗狀態可辨識。

### Phase C：回報工作流

- 回報收件匣、回報 detail、原始資料／照片／心得、AI 狀態、Correction／Archive。
- Draft 與志工手機流程共享同一 CRM contract；不建立前端獨立回報資料。
- Gate：人工回報先保存；AI 或 Media 失敗不阻擋，Correction／Archive 可追溯。

### Phase D：收容所營運設定

- 收容所、帳號、Membership、Cage／Area、QR、Reportable Scope、觀察語彙整合於 Settings。
- 依角色顯示可操作欄位與批次／單筆操作；所有異動顯示成功、失敗與 Audit 連結。
- Gate：管理員只能操作所屬 Shelter；平台管理員的平台 Scope 可跨 Shelter 且每次可稽核。

### Phase E：AI／Audit 與真人驗收

- AI 待覆核佇列、人工確認／修正、Audit 查詢、失敗重試狀態。
- 以同一工作台腳本執行工作人員真人驗收，不用「知道深層網址」取代可發現性測試。
- Gate：SC-006／SC-014 通過；志工流程另依 SC-001／SC-002 驗收。

## 8. 明確不做

- 不在這一輪把每個現有 endpoint 各自包成孤立頁面。
- 不在前端自行計算權限、跨租戶範圍、AI 狀態或回報正式狀態。
- 不把 `ORG-A`、第一隻動物或目前 URL 寫成正式產品的唯一入口。
- 不增加公開動物頁面、批次 Export、通知、完整排班或醫療診斷功能。

## 9. 完成定義

整體管理工作台只有在以下條件都成立時才視為完成：

- 登入、Context、角色導航與直接 URL 存取行為一致。
- 工作人員可從首頁經動物清單／搜尋在三次主要操作內進入指定 Timeline。
- 管理員可在同一 Shell 完成所屬 Shelter 的帳號、範圍、QR 與語彙管理。
- 回報、Timeline、AI 與 Audit 均能追溯 CRM 原始資料，沒有前端正式副本。
- A／B 隔離、自動化品質 Gate、SC-006／SC-014 真人證據均通過；未通過時維持
  `In Progress`／不可部署狀態。
