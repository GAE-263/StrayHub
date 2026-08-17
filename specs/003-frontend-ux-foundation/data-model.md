# 資料模型：前端 UX Foundation

本功能不新增 CRM 業務資料表、API entity 或前端業務資料副本。以下模型是 UI contract 與驗收所需的呈現狀態，所有業務資料仍由既有服務與 CRM 提供。

## UIStatusState（介面狀態）

所有 P0／P1 頁面以 `StatusView` 作為 `UIStatusState` 的 canonical rendering composition；`EmptyState`、`ErrorState` 與 `StatusBanner` 只作為既有 presentation adapter。本功能不加入 shadcn `Empty`，空資料由 `kind: empty` 表示。

### 欄位

| 欄位 | 規則 | 用途 |
| --- | --- | --- |
| `kind` | `loading`、`saving`、`success`、`empty`、`no-results`、`error`、`permission-denied`、`processing`、`ai-failed`、`needs-review` | 決定狀態語意與可用操作；`saving` 是獨立於讀取 `loading` 的寫入狀態 |
| `title` | 必須是台灣繁體中文、可獨立理解 | 畫面主要狀態標題與必要的 live announcement |
| `description` | 可選但錯誤、權限、空資料與 processing 通常必須提供 | 解釋原因、限制與下一步 |
| `action` | 可選；最多提供目前情境可安全執行的主要下一步 | 重試、清除條件、返回、聯絡管理者或人工覆核 |
| `tone` | 由 `kind` 對應到 semantic token；不得任意以頁面色碼覆寫 | Alert、Badge、Toast 與 focus／icon 的一致視覺語意 |
| `ariaLive` | `polite` 用於 loading／saving／success／processing／`ai-failed`／needs-review；`assertive` 只用於阻斷性錯誤 | 輔助科技取得必要回饋；同一保存請求不得重複播報 |

### 不變條件

- `empty` 只代表請求成功且沒有資料；不能用來代表請求尚未完成、請求失敗或沒有權限。
- `loading` 只代表讀取或初始化資料尚未完成；`saving` 只代表使用者觸發的寫入請求尚未完成，兩者不得互相替代。
- `saving` 必須保留可恢復的原始輸入、阻止同一主要操作重複提交；成功轉為 `success`，失敗轉為 `error` 並保留輸入。
- `no-results` 必須保留目前搜尋／篩選脈絡，並提供清除或調整條件。
- `error` 不得清空可安全保留的既有內容，不得洩漏跨收容所或內部敏感資訊。
- `permission-denied` 不得提供受保護資料、筆數或可推測其他收容所存在性的資訊。
- `processing` 與 `needs-review` 只表示工作流程狀態，不代表 AI 或系統已完成正式決定；完成後回到 canonical `success` 狀態。
- `ai-failed` 表示 AI 無法使用，但原始回報已保存；不得顯示成原始資料保存失敗，也不得阻止人工流程。

## ManagementContext（管理工作情境）

這是由既有登入與目前收容所服務提供的 runtime view，不新增持久化 entity。

| 欄位 | 來源／規則 | UI 用途 |
| --- | --- | --- |
| `userDisplayName` | 既有登入使用者資料 | Header 與登出情境 |
| `role` | 既有 platform role 或 membership role | 導覽與操作可見性 |
| `activeOrganizationId` | 既有已驗證 Active Shelter Context | 所有受保護資料的顯示範圍 |
| `organizationLabel` | 既有 organization code／name | Context selector／pill |
| `organizations` | 既有已授權組織集合 | 只有可切換時顯示 context selector |
| `pathname` | 目前頁面位置 | active navigation、Breadcrumb、返回語意 |

### ShelterManagementView（P1）

`/shelters` 是 P1 的管理頁面 view，不是新的持久化 entity。它只組合既有的登入者、角色、已驗證 Active Shelter Context 與 organization scope；頁面可見操作必須依既有授權結果呈現，不能由 pathname、query string 或前端 state 推導新的權限。P1 的 shelter management 不得成為 P0 門檻的依賴，也不得建立跨租戶資料副本。

### 不變條件

- UI 不信任 URL、sessionStorage、表單或 query string 的 organization id 作為授權依據。
- `activeOrganizationId` 變更必須先完成既有服務確認；失敗時保留舊情境或回到安全錯誤狀態。
- `role` 只能縮小可見操作，不得由 UI 擴大後端授權。

## DesignTokenSet（設計 token）

### 語意 token 類別

| 類別 | 最低 token | 使用規則 |
| --- | --- | --- |
| Surface | `background`、`surface`、`surface-muted`、`overlay` | 頁面、Card、Dialog 與遮罩層 |
| Content | `foreground`、`muted-foreground`、`inverse` | 主要、次要與反差文字 |
| Border／focus | `border`、`input`、`ring` | 分隔線、欄位邊框與鍵盤焦點 |
| Action | `primary`、`primary-foreground`、`secondary`、`secondary-foreground` | Button 與主要連結 |
| Status | `success`、`warning`、`destructive`、`info` | Alert、Badge、狀態圖示與文字 |
| Shape | `radius-sm`、`radius-md`、`radius-lg` | input、button、card、dialog 的一致圓角 |
| Depth | `shadow-sm`、`shadow-md`、`shadow-overlay` | 只在需要區分層級時使用 |
| Type／space | typography scale、line-height、spacing scale | 文字階層、表單密度與頁面留白 |

### Token 不變條件

- 所有 status token 必須在白色、surface-muted 與 overlay 上維持可讀對比；狀態仍需有文字或其他語意。
- focus ring 不得被背景、border 或 Dialog overlay 隱藏。
- P0 不直接在 page component 散落現有 hex 色碼或重複 shadow／radius 宣告。
- token 調整不應改變既有 API、資料或權限行為；視覺回歸由 screenshot baseline 捕捉。

## NavigationItem（導覽呈現模型）

| 欄位 | 規則 |
| --- | --- |
| `href` | 沿用既有管理路由；不可因 UI 遷移造成深連結失效 |
| `label` | 台灣繁體中文主要名稱；必要時保留英文 technical code 為次要文字 |
| `group` | 工作台或設定與治理 |
| `roles` | 既有角色過濾；缺省代表既有可見範圍 |
| `active` | 由目前 pathname 與既有 nested route 規則決定 |
| `icon` | Lucide semantic icon；icon-only 時必須有名稱，導航項目通常保留可見文字 |

## ResponsiveMode（響應式模式）

| 模式 | 驗收寬度 | 主要行為 |
| --- | --- | --- |
| `mobile` | 360px | 單欄、Sheet 導覽、卡片／展開 row、44px 觸控區域 |
| `compact-mobile` | 480–639px | 單欄、filter 堆疊、次要操作收進 Sheet／Dropdown |
| `tablet` | 768px | 兩欄可用、filter 可分行、資料表保留主要資訊 |
| `desktop` | 1024px | Sidebar、完整管理資訊與 Breadcrumb |
| `wide-desktop` | 1280–1440px | 限制內容最大閱讀寬度，避免過度分散 |

## 元件變體契約

### Button

- `variant`: `default`、`secondary`、`ghost`、`destructive`、`link`。
- 主要 action 使用可見動詞；危險 action 使用 `destructive` 加確認流程。
- pending／disabled 狀態不得產生重複提交；不可用時仍保留可理解的 accessible name。

### Badge

- `variant` 由 domain wire value 經 mapping 產生，不直接把 wire value 當成主要文案。
- 至少支援 active／disabled／archived／saved／amended／processing／failed／needs-review／source 等語意。
- Badge 文字必須能獨立表達狀態；顏色與 icon 是輔助訊息。

### Field

- 每個欄位有唯一 label；description 與 error 透過 id 關聯。
- invalid、pending、disabled 與 read-only 狀態在視覺與輔助科技上可辨識。
- 保存失敗保留可恢復的使用者輸入。

### Dialog／Sheet

- 規格中的 Drawer 是手機側向抽屜的產品語意；UI foundation 統一以 Sheet 實作，不另建立 Drawer component 或互動 contract。

- 開啟後 focus 進入合理的標題／第一個操作；關閉後 focus 回到 trigger 或下一個合理控制。
- Escape、取消與 overlay 行為遵循元件契約；高風險操作使用 AlertDialog。
- 手機 Sheet 不得讓使用者失去主要頁面位置或目前情境。

## 狀態轉換檢視

```text
idle ──request──> loading ──success──> success / empty / no-results
                     │
                     └──failure──> error / permission-denied

idle ──save──> saving ──success──> success
                 │
                 └──failure──> error (保留原始輸入)

saved report ──AI job──> processing ──result──> needs-review or success
                              │
                              └──failure──> ai-failed (原始回報仍保存)
```

## 持久化與遷移

- 本功能不建立 migration、不新增資料 entity、不修改既有 response shape。
- `DesignTokenSet`、`UIStatusState`、`NavigationItem` 與 `ResponsiveMode` 都是 UI 層 contract，不得被儲存成 CRM 業務資料。
- 舊 class 在遷移完成前可以作為 presentation fallback；其移除必須由 route grep、browser screenshots、a11y 與品質門檻共同證明。
