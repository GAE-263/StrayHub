# UI 行為契約：前端 UX Foundation

本文件定義 P0／P1 的可觀察 UI 行為。它不指定 React component 實作，但規定使用者、輔助科技與測試可以觀察到的結果。

## 1. 管理工作台 Shell

- 管理頁面必須顯示目前頁面、目前收容所與登入者可辨識名稱。
- 桌面模式提供工作台導覽；手機模式由可明確開啟與關閉的側欄面板提供相同導覽。
- 只有已授權角色的導覽與操作可見；不可用 UI 隱藏不等於後端授權，後端 scope 不變。
- Active Shelter Context 切換中、成功、失敗與缺少 context 都必須有明確狀態；切換失敗不能以新收容所內容冒充成功。
- 登出後不得繼續以舊頁面 state 查看受保護內容。

## 2. 導覽與圖示契約

- 導覽項目與主要操作使用台灣繁體中文可見文字；英文 code 只能作為次要資訊。
- Lucide icon 必須與操作語意相符：搜尋、返回、展開、收合、編輯、停用、重試、設定、AI、權限等不可任意互換。
- icon-only control 必須有 accessible name；若使用者需要額外理解，提供 Tooltip，但 Tooltip 不取代必要的 label。
- 圖示不得成為唯一狀態訊息；狀態要同時有文字或其他可讀語意。

## 3. Button、Badge 與 Card

- Button 以動詞表達動作；主要、次要、低優先與危險操作的視覺與語意一致。
- `saving` 是獨立於讀取 `loading` 的保存中／送出中狀態；主要按鈕在 `saving` 時不可重複觸發同一個操作，且使用者輸入必須保留。
- Badge 顯示使用者可理解的狀態名稱；狀態不只靠顏色。
- Card 只用於形成清楚的內容區塊；不可將所有文字堆疊成無差異卡片，主要資訊仍依資訊階層呈現。

## 4. 表單契約

- 每個欄位有可見或可由輔助科技取得的 label。
- description、validation error 與 field 的關聯可被鍵盤與螢幕閱讀器取得。
- 保存失敗、網路中斷或資料衝突時，保留可恢復的使用者輸入並提供重試／重新確認方式。
- 志工回報表單不因 UI migration 增加不必要的必填欄位或步驟。

## 5. Dialog 與 Sheet 契約

- 本 contract 中的 Drawer 是產品互動語意；手機側向 Drawer 統一以 `Sheet` 呈現，不另建立 Drawer primitive 或另一套 focus／keyboard 規則。
- Dialog 用於編輯或補充內容；AlertDialog 用於停用、封存、登出或其他需要確認影響的操作。
- 開啟時使用者知道標題、目的與目前情境；關閉後焦點回到 trigger 或合理的下一個控制。
- Escape、取消與明確的取消按鈕不能造成資料或狀態改變。
- 手機側欄以 Sheet 呈現時，開啟、關閉、Escape、focus trap 與 focus restore 都可驗證。

## 6. Table 與響應式資料契約

- 桌面表格可保留完整欄位；手機只保留完成主要任務所需的主要欄位，其餘資訊以 detail／展開方式取得。
- 動物、回報與 Timeline 不得因手機轉卡片而遺失日期、動物身分、同日多筆、原始心得、照片數量、AI 狀態或人工狀態。
- 搜尋／篩選後要能辨識目前條件與結果；無結果與載入失敗不可使用相同呈現。

## 7. 狀態契約

`StatusView` 是所有 P0／P1 頁面的 canonical state composition。`EmptyState`、`ErrorState` 與 `StatusBanner` 只能作為遷移期間的 adapter 或既有名稱，不得建立與 `StatusView` 不一致的狀態語意；本功能不加入 shadcn `Empty` 元件。

| 狀態 | 必要內容 | 必要下一步 |
| --- | --- | --- |
| Loading | 正在取得的資料或流程 | 等待；必要時保留既有內容 |
| Saving | 正在保存，已保留輸入；不得與 Loading 混淆 | 等待；禁止重複提交；失敗時重試且保留輸入 |
| Empty | 沒有資料的原因或目前範圍 | 建立、返回或查看說明 |
| No results | 目前搜尋／篩選條件摘要 | 清除或調整條件 |
| Error | 安全且繁體中文的錯誤說明 | 重試、重新載入或返回 |
| Permission denied | 不洩漏受保護資料的權限說明 | 返回或聯絡管理者 |
| Success | 實際完成的動作 | 繼續、查看結果或關閉回饋 |
| AI processing | 原始回報已保存且 AI 尚在處理 | 等待或前往其他工作 |
| AI failed (`ai-failed`) | AI 無法使用，但原始回報仍存在 | 人工查看、重試或稍後處理 |
| Needs review | 結果需要授權人員確認 | 開啟人工覆核 |

`Saving` 的狀態轉換為 `idle → saving → success` 或 `idle → saving → error`；保存成功後才可顯示成功回饋，保存失敗必須回到可修正／可重試的錯誤狀態。`Saving` 的 live region 使用 `aria-live="polite"`，同一保存請求不得因重複 render 或背景輪詢重複播報。

## 8. 響應式契約

- `360px`：單欄、主要操作可見、導航用 Sheet、核心內容無非必要水平溢出。
- `768px`：可使用兩欄或分組 layout，filter 與內容仍保持可讀。
- `1024px`：管理 Shell 顯示完整 Sidebar 與主要工作區。
- `1440px`：內容使用合理 max width，避免閱讀距離過寬。
- 所有尺寸：長中文名稱、長錯誤、放大文字、狀態 badge 與主要操作不得互相重疊或被截斷。

## 9. 無障礙契約

- 頁面與區段標題階層合理；目前頁面、目前收容所與主要操作有可理解名稱。
- 所有核心流程可用鍵盤完成；focus visible 且不被 sticky header、Sheet 或 Dialog 遮擋。
- status、error、success、loading、saving、permission 與 AI state 依阻斷程度使用合適的 live region，不重複或過度播報。
- `processing` 與 `ai-failed` 使用 `aria-live="polite"`，只在狀態首次變更或使用者主動重試後播報；背景輪詢不得反覆播報相同內容。
- `needs-review` 使用 `aria-live="polite"`，並明確說明結果需要授權人員確認。
- `ai-failed` 必須說明原始回報已保存，不得播報成原始回報保存失敗。
- color、icon、位置與形狀不可是必要資訊的唯一通道。
- P0 必須通過自動 axe baseline、Playwright keyboard smoke 與人工 VoiceOver checklist。

## 10. 資料與授權契約

- UI 不改變既有 API、CRM、歷史 snapshot、AI raw output、人工 review 或 organization scope。
- 所有資料查詢仍由既有已驗證 context 與服務 boundary 決定；頁面中的 query string、sessionStorage 或 component state 不得成為授權來源。
- A／B 收容所即使有相同 shelter number 或 stable code，也不得在 UI 結果、數量、狀態或錯誤中互相洩漏。
- P0 失敗降級時，原始志工回報仍可保存，AI 失敗不阻止人工流程。

## 11. P1 收容所管理契約

- `/shelters` 是 P1 route；完成 US5 的 P0 browser／responsive／keyboard／screen reader／visual evidence 後即可開始，並可與 P0 收尾平行，不是 P0 門檻的依賴。
- `/shelters` 沿用管理 Shell、StatusView、表單、權限與 Sheet／Dialog contract；不建立第二套頁面狀態或 overlay 語意。
- 只有既有授權角色可看到 shelter management 操作；UI 不取代後端授權，前端不得把 pathname、query string 或 local state 當成 permission source。
- 目前已驗證的 Active Shelter Context 與 tenant scope 決定可見資料與操作；ORG-A／ORG-B 不得因相同 shelter number、名稱或錯誤訊息而互相洩漏。
- loading、saving、empty、error、success、permission denied 與 destructive action confirmation 必須沿用 `StatusView`、Alert 或 AlertDialog 的既有語意；P1 evidence 不納入 P0 門檻。
