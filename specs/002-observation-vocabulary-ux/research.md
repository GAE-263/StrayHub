# 研究與設計決策：觀察詞彙管理介面資訊架構與可讀性優化

**Feature**：[spec.md](spec.md)
**研究日期**：2026-08-11

## 研究範圍

本階段檢視既有觀察詞彙 API、SQLAlchemy model、Repository／Service、Alembic migration、照護回報快照、AuditService、管理工作台、OpenAPI 生成流程與既有測試。專案沒有 `before_plan` 或 `after_plan` extension hook。

現況重點：

- `apps/web/app/(management)/settings/observation-options/page.tsx` 將類別、建立表單與所有選項平鋪在同一頁，已有中文與英文 code 混排、改名、上下移、停用與 `requires_note` 新增，但沒有分組收合、搜尋／篩選、摘要、封存、編輯表單或確認對話。
- `services/api/app/api/observation_options.py` 已提供類別列表、選項列表、建立、PATCH 更新與 reorder；目前 update 沒有 `requires_note`、code 或封存生命週期，且 `OPTION_MANAGER_ROLES` 將 `STAFF` 也列為可管理者。
- `ObservationOption` 目前只有 `active`／`disabled` 語意，來源由 `organization_id is null` 推導；現有 Repository 只允許同一收容所讀取平台預設與自己的自訂資料。
- `CareReport.answer_snapshots` 已保存回報建立時的 code 與顯示名稱；它是歷史顯示相容性的既有基礎，但資料欄位是 JSON，不能把目前選項名稱回填覆蓋舊快照。
- `AuditService` 已能保存 organization、actor、action、resource、before／after、source channel 與 reason，可直接延伸觀察選項稽核，不需要另建第二套稽核來源。
- `packages/contracts/src/openapi.ts` 是生成檔；目前 source-of-truth 在既有 feature 的 `specs/001-volunteer-care-report/contracts/openapi.yaml`，實作時需同步該契約並重新產生型別。

## Decision 1：沿用既有 HTTP 路徑，擴充回應與狀態動作

**Decision**：保留 `/v1/observation-categories`、`/v1/observation-options`、`/v1/observation-options/{optionId}` 與 `/v1/observation-options/reorder`，在不破壞既有欄位的前提下新增摘要、類別計數、最後修改資訊、歷史使用旗標與 `archived` 狀態。新增明確的 disable、restore、archive 動作路徑；不新增 DELETE。

**Rationale**：既有管理頁與 Bot／回報流程已依賴同一組觀察選項 API，沿用路徑可降低跨入口漂移。`enabled` 仍可保留為相容欄位，但不能表達停用與封存的差異，因此生命週期使用明確動作與 Audit action。

**Alternatives considered**：

- 新建 `/v1/management/observation-vocabulary` 聚合服務：拒絕，會製造與既有 effective options 來源平行的資料讀取邊界。
- 只把所有邏輯放在前端：拒絕，無法落實權限、租戶隔離、歷史使用鎖定與稽核。
- 只把 `enabled` 改成布林值：拒絕，無法區分已停用與已封存，也無法讓恢復／封存的稽核語意清楚。

## Decision 2：對目前規模採一次載入、前端組合篩選與漸進式揭露

**Decision**：管理頁載入目前收容所的所有可查看選項及 13 個類別資料；前端以純函式 selector 完成中文名稱／stable code／說明搜尋、類別／狀態／來源 AND 篩選、分類、計數與收合狀態。初次只渲染類別摘要；展開後先渲染收容所自訂，再顯示可獨立收合的平台預設區段。

**Rationale**：規格將目前規模定為約 500 個選項，既有 API 也已一次回傳有效與歷史選項；一次載入能讓四項總摘要不受目前篩選影響，也避免搜尋每次輸入造成多次權限查詢。所有操作仍在已驗證的收容所資料範圍內，前端篩選只是呈現層，不是安全邊界。

**Alternatives considered**：

- 每個類別分別請求：拒絕，增加請求數與載入狀態複雜度，且難以保證摘要與各區塊使用同一資料截面。
- 所有搜尋與篩選都新增伺服器 query：暫不採用，對目前 500 筆上限是過度設計；若後續超過容量或出現分頁需求，另立契約變更。
- 初次直接展開全部：拒絕，與降低長清單負擔的核心目標相反。

## Decision 3：保留 wire source，將顯示名稱改為台灣繁體中文

**Decision**：API 仍保留 `source: platform_default | organization_extension`，前端與文件把 `organization_extension` 顯示為「收容所自訂」。平台預設選項由 `organization_id is null` 判定，收容所自訂只允許目前 Organization 的資料。

**Rationale**：現有 generated types、Bot effective option mapping 與隔離測試已使用 `organization_extension`；只改顯示文案即可達成使用者語言目標，不會讓下游以為來源值改變。資料來源判定仍由後端推導，不信任前端傳入 source。

**Alternatives considered**：

- 直接把 wire enum 改成 `shelter_custom`：拒絕，會造成既有 client 與 generated contract 不相容。
- 只在前端隱藏來源：拒絕，歷史與稽核也需要明確來源語意。

## Decision 4：沿用現行 effective stable code 唯一規則

**Decision**：stable code 以目前收容所可見的完整有效詞彙範圍為唯一範圍，包含平台預設與收容所自訂；接受既有小寫英文字母、數字、底線與句點格式。新增與未使用自訂選項的 code 修改都必須做格式與唯一性檢查；已被歷史回報使用的 code 鎖定。

**Rationale**：既有 `ObservationOptionService` 的 `option_code_exists` 已以整個 effective vocabulary 檢查 code，既有 unit test 也驗證不同 category id 仍不得重複。保留現行語意比改成只在類別內唯一更安全，也不會讓後續回報 code 產生歧義。

**Alternatives considered**：

- 改成只在同一 category 唯一：拒絕，與現有服務與測試行為衝突，且可能讓回報 code 在不同 category 間難以判讀。
- 所有自訂 code 建立後永久不可改：較安全但不完全符合規格對未使用 code 的修正需求；以歷史使用索引做條件鎖定。

## Decision 5：以可重建使用索引判斷歷史使用

**Decision**：新增 `observation_option_usages` 衍生索引，記錄 Organization、CareReport、category code、option code、當時 display name／說明快照與可對應的 ObservationOption id。它只用於 `has_historical_usage`、usage count 與 code 編輯／永久刪除保護；正式來源仍是 `care_reports.answers`、`care_reports.answer_snapshots` 與 corrections。新回報提交及回報觀察修正時在同一交易補入索引；migration 從既有 snapshot 優先、缺少 snapshot 時從 answers 回填，無法對應目前 option 的舊 code 仍保留為不可誤刪的 orphan usage。

**Rationale**：既有歷史答案放在 JSON，逐一掃描每個 option 會讓管理頁成本與資料完整性難以預測。可重建索引能把「是否被使用」變成明確、可查詢、可稽核的關係，同時遵守 CRM 唯一事實來源：索引可以從 CRM 回報重建，不能取代快照。遇到索引無法確認時採 fail-closed，code 不允許修改。

**Alternatives considered**：

- 只依 `answer_snapshots` JSON 搜尋：拒絕，舊資料可能只有 answers，且 500 筆選項下逐一 JSON 搜尋風險較高。
- 在 ObservationOption 直接保存 usage count：拒絕，計數容易因回報修正、歷史回填或資料復原而漂移，無法提供可重建證據。
- 讓所有 code 永久不可變：可行但會縮減規格允許的未使用 code 修正，保留索引可在不犧牲追溯的情況下提供較完整管理能力。

## Decision 6：狀態與安全規則

**Decision**：Option 狀態為 `active`、`disabled`、`archived`；`enabled` 是向後相容的 `status == active` 衍生值。只有收容所自訂選項可由收容所管理者執行狀態轉換；平台預設在此頁唯讀。所有自訂選項都不提供硬刪除，任何已使用選項至少可停用或封存；恢復會把自訂項目回到 active，並保留歷史快照與稽核。

**Rationale**：把狀態轉換從 PATCH 布林值分離，可以在 API、UI 確認與 AuditRecord 中明確表達停用、恢復與封存；永不硬刪除也讓既有歷史回報不會失去可解析的對象。

**Alternatives considered**：

- 只支援 active／disabled：拒絕，規格要求可區分封存，且未來需要把長期歷史資料與一般停用區分。
- 允許未使用項目永久刪除：拒絕，本 MVP 以單一非破壞性生命週期簡化使用者心智模型並避免誤刪。

## Decision 7：角色能力沿用現有管理權限，不新增細粒度 RBAC

**Decision**：GET 允許現有 management context 的 Staff 讀取，但 Staff 只收到啟用中的詞彙與唯讀資訊；建立、編輯、排序、停用、恢復、封存只允許現有 admin context（`SHELTER_ADMIN` 與具有效 Shelter Context 的 `PLATFORM_ADMIN`）。Volunteer 無查看或管理權限。若未來要授權特定 Staff，另立權限規格，不在本 MVP 偷渡新的 permission schema。

**Rationale**：現有 `require_admin_context` 已明確表達 settings 管理邊界，現行 option API 卻把 Staff 放進 mutation role 集合，這是本功能需要修正的安全缺口。沿用既有角色可避免新增難以驗收的細粒度權限資料模型。

**Alternatives considered**：

- 所有 Staff 都可管理：拒絕，與規格「一般工作人員不受管理細節干擾」及最小權限衝突。
- 新增每個使用者的觀察詞彙 permission：暫不採用，會擴大 MVP、需要帳號管理 UI 與權限稽核規格。

## Decision 8：最後修改資訊從 AuditRecord 與更新時間組合

**Decision**：回應提供 `last_modified_at` 與 `last_modified_by` 顯示資料；時間沿用 ObservationOption 的 `updated_at`，操作者由該 option 最新的 AuditRecord 解析，平台預設若沒有收容所稽核則顯示「平台預設／系統」。不另建容易與稽核漂移的 owner 欄位。

**Rationale**：AuditRecord 已保存 actor、時間與 before／after；重用它可同時滿足列表可讀性與完整稽核，且不把 audit metadata 拆成第二個事實來源。

**Alternatives considered**：

- 在 ObservationOption 新增 `last_modified_by` 欄位：拒絕，會讓直接資料異動、migration 與稽核紀錄可能產生兩套結果。
- 列表不顯示最後修改者：拒絕，未達規格的管理可追蹤性與使用者信任需求。

## Decision 9：契約與生成型別流程

**Decision**：在本 Feature 的 `contracts/observation-vocabulary.yaml` 固定新增／修改的 HTTP contract；實作時同步到專案既有 canonical `specs/001-volunteer-care-report/contracts/openapi.yaml`，再執行 `npm --prefix packages/contracts run generate` 與 `check`。`packages/contracts/src/openapi.ts` 永遠不直接編輯。

**Rationale**：專案 README 與 package script 已指定既有 OpenAPI 為 HTTP source-of-truth，且 generated types 有漂移檢查。Feature-local contract 讓本次設計可審查，canonical contract 同步則讓實作與既有 clients 不分裂。

**Alternatives considered**：

- 只更新 TypeScript generated file：拒絕，生成檔不可作為契約來源。
- 為本 Feature 建立第二個正式 OpenAPI 來源：拒絕，會造成服務契約分裂；Feature-local 文件只作設計差異，正式合併時回到 canonical source。

## Decision 10：測試與驗證策略

**Decision**：沿用既有測試分層，新增純 selector／validation unit tests、API／migration integration tests、A／B RLS isolation tests、OpenAPI contract tests、管理頁互動與 responsive／a11y tests，以及回報／timeline 歷史快照 regression。Quickstart 只使用虛構本機 seed，先跑 targeted tests，再跑現有 local quality gate。

**Rationale**：這個功能同時變更 UI、權限、資料狀態與歷史相容性，單一前端測試不能證明 CRM 及租戶隔離安全；分層測試能讓 P0 核心在無 AI／LINE／GCP 時獨立驗收。

**Alternatives considered**：

- 只做頁面 snapshot test：拒絕，無法驗證狀態轉換、稽核、RLS 或回報歷史。
- 直接跑完整 `verify_local.sh` 作為唯一回饋：拒絕，回饋速度慢且無法定位規格情境；先 targeted，再完整 gate。

## 未解決問題

本階段沒有保留未解決的釐清標記。未來若資料量實際超過規格的約 500 個選項、需要授權特定 Staff，或要支援跨收容所詞彙匯入，應建立獨立規格或更新本 Feature，而不是在本次實作中默默擴張範圍。
