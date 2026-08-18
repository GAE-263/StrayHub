# Research: 收容所權限管理介面改善

## Decision 1：在 Membership list response 內提供使用者身份投影

- **Decision**：清單 response 增加 `username` 與 `display_name`，由 organization-scoped membership query 同時取得，前端以 `display_name` 為主、`username` 為輔。
- **Rationale**：目前頁面只有 `user_id` UUID，管理員無法可靠辨識操作對象；User 已是 CRM 既有事實來源，直接投影既有欄位不會建立第二份資料。
- **Alternatives considered**：
  - 前端逐筆呼叫使用者詳情：會造成 N+1 查詢，也增加跨租戶資料誤用風險。
  - 只在前端維護 UUID 對照表：不是 CRM 事實來源，且資料容易過期。

## Decision 2：以 organization-scoped join 限制身份資料

- **Decision**：Membership 清單在同一個 organization query 中關聯 User，保留既有 Membership authorization gate；沒有對應身份資料時回傳空值，由 UI 顯示安全的未命名提示。
- **Rationale**：清單本身已先驗證目前收容所管理權限；同一個 organization predicate 可使身份投影與 Membership 範圍一致，避免為了顯示名稱而暴露其他收容所使用者。
- **Alternatives considered**：
  - 由 client 傳 user id 再查詢：會把授權範圍交給不可信輸入，違反多租戶隔離原則。
  - 回傳所有平台使用者供前端篩選：會過度暴露個人資料，且不符合最小權限。

## Decision 3：用現有 UI primitives 與 CSS media queries 重排 Membership

- **Decision**：保留現有 Card、Badge、Select、Button 與表單操作，新增 Membership identity／meta／actions 區塊與 1080px、600px 重排規則。
- **Rationale**：這是既有頁面的呈現改善，不需要引入新的元件或第三方 layout library；分層卡片可同時改善桌面閱讀與手機操作尺寸。
- **Alternatives considered**：
  - 改成完整資料表：手機需要水平捲動，無法解決擁擠問題。
  - 以可折疊 accordion 隱藏操作：會增加管理員尋找權限狀態的步驟，不符合快速辨識目標。

## Decision 4：時區只顯示固定政策，不提供頁面 mutation

- **Decision**：頁面顯示 `Asia/Taipei` 統一使用說明，移除時區 select 與儲存按鈕；本 feature 不移除既有後端欄位或改寫其他功能的時區資料模型。
- **Rationale**：使用者明確表示服務對象為台灣各地收容所，頁面修改時區沒有實際需求，移除控制可避免誤改日期依據。
- **Alternatives considered**：
  - 保留 disabled select：仍會讓使用者以為時區可被維護，且留下不必要的設定負擔。
  - 修改整個 organization timezone model：超出本次 `/shelters` UX 範圍，並可能影響醫療提醒與既有資料。

## Decision 5：驗證採分層測試與本機真人流程

- **Decision**：以 page Vitest 驗證角色可見性、身份呈現與時區控制；以 TypeScript／contract tests 驗證欄位一致性；最後使用 `local-shelter-admin-a` 在本機 `/shelters` 驗證身份、layout 與既有操作可見性。
- **Rationale**：UI 變更與 API read projection 分屬不同邊界，分層驗證可以在不依賴完整外部環境時快速定位問題，再用真人流程確認組合結果。
- **Alternatives considered**：只依賴單一 E2E：失敗時難以區分 API contract、授權或 CSS 問題，且不容易覆蓋非視覺的欄位契約。
