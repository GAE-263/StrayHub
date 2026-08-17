# UI 契約

本功能沒有新增或修改 HTTP／資料庫契約。既有 OpenAPI 與後端授權邊界仍是唯一資料服務來源；本目錄只記錄前端 UI、互動、響應式與可及性契約，供實作與驗收共同使用。

## 契約清單

- [ui-behavior.md](ui-behavior.md)：P0 Shell、元件、狀態、responsive、icon、keyboard、focus 與資料邊界。

## 保留的既有契約

- `specs/001-volunteer-care-report/contracts/openapi.yaml`：既有 HTTP contract，這次不得改變。
- `packages/contracts/src/openapi.ts`：既有 generated TypeScript contract，這次不得手動改寫。

## 契約變更政策

- UI migration 若發現既有資料不足，不得直接在前端建立替代業務資料；應另開需求評估既有服務 contract。
- 新增的 UI state、token、variant 與 responsive 規則必須能以 browser／component test 驗證。
- 任何造成既有 route、role、organization scope、original report、AI review 或 timeline snapshot 行為改變的需求，必須拆成獨立 spec。
