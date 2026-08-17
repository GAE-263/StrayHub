# Contracts：動物醫療與照護提醒

本目錄是 feature 006 的 additive design contract，不是獨立 production source of truth。

- `medical-care.openapi.yaml`：新 endpoint、request／response 與錯誤 shape。
- `authorization.md`：角色、capability、指派與租戶可見性。
- `timeline-and-calendar.md`：時區、Agenda bucket、virtual occurrence、Timeline additive schema。

實作順序：

1. 審查本目錄契約。
2. 將 paths／components 合併到 `specs/001-volunteer-care-report/contracts/openapi.yaml`。
3. 執行 `npm --prefix packages/contracts run generate`。
4. 執行 `npm --prefix packages/contracts run check`，確認 `packages/contracts/src/openapi.ts` 無 drift。
5. FastAPI 以具名 Pydantic model 實作相同 schema；前端由 generated contract 推導 DTO。

契約中的 write payload 不接受 `organization_id`。租戶只從已驗證 session／active organization context 取得。

合併 canonical contract 時，除本檔新 paths 外，既有 organization／membership／current-context schemas 也要引用 `OrganizationMedicalSettings`、`MembershipMedicalCareAccess` 與 `MedicalCareCapabilitySummary`，使 timezone 與 effective capability 有單一可產生型別的定義。
