# Research: 平台管理員人數與替換治理

## Decision 1: 沿用 User 的平台角色與帳號狀態

- **Decision**: `User.platform_role = PLATFORM_ADMIN` 是平台管理員權限的唯一角色來源；`User.status = active` 才計入啟用中的平台管理員。降權將平台角色清除，停用則沿用既有 User status，兩者都保留 User 與 Membership 歷史。
- **Rationale**: 現有登入、RequestContext 與 `require_platform_admin` 已以這兩個欄位判斷平台 scope；沿用可避免建立第二套平台身分，並維持平台管理員不需要 Membership 的既有設計。
- **Alternatives considered**: 新增獨立 PlatformAdminUser 表會造成 User、登入與稽核資料分裂；把平台角色寫入 OrganizationMembership 會違反平台層級與收容所層級分離。

## Decision 2: 以單一治理政策資料列保存上下限並提供鎖定點

- **Decision**: 新增單一 `PlatformAdminPolicy` 資料列，保存 `min_active_admins = 1` 與 `max_active_admins = 2`。每次平台管理員新增、提升、啟用、停用、降權與替換，都在同一交易先鎖定此資料列，再重新計算最新啟用人數與執行狀態轉換。
- **Rationale**: PostgreSQL 的一般欄位 constraint 無法直接限制跨多筆 User 的啟用角色數量；單一政策資料列同時提供明確政策來源與所有治理異動共用的 row lock，可避免並發操作突破上下限或留下半套替換結果。
- **Alternatives considered**: 只在 service 內使用常數無法提供跨請求鎖定；只使用資料庫 advisory lock 不保存政策來源；只依賴 UI 或單次 count 查詢會有競爭條件。

## Decision 3: 平台管理員使用獨立 global route

- **Decision**: 提供 `/platform-admins` 管理頁與 `/v1/platform/administrators` API；所有查詢與異動只要求啟用中的 `PLATFORM_ADMIN`，不要求 Active Shelter Context，也不以組織 Membership 作為範圍。
- **Rationale**: 平台管理員是跨收容所的 platform scope；混入 `/shelters` 會讓 organization-scoped 成員清單承擔不同的資料邊界，容易讓 UI 與授權語意混淆。
- **Alternatives considered**: 在 `/shelters` 增加平台管理員區塊會把全域帳號與單一收容所 Membership 混在一起；要求先選收容所會把不必要的租戶 context 引入全域治理操作。

## Decision 4: 支援建立全域帳號、提升既有帳號與替換

- **Decision**: 管理流程提供兩種新增來源：建立沒有 Membership 依賴的全域平台管理員帳號，或提升既有啟用帳號。當已有兩位啟用中的平台管理員時，一般建立／提升拒絕，必須使用一次確認的新舊替換流程。
- **Rationale**: 平台管理員不應被迫先建立收容所 Membership；同時保留把既有可信帳號提升為平台管理員的彈性。替換流程避免先降權舊管理員而無法新增新管理員。
- **Alternatives considered**: 只允許提升既有帳號無法處理沒有既有 Membership 的平台治理帳號；只允許建立新帳號則無法安全重用現有受管理帳號。

## Decision 5: 沿用平台稽核，不建立第二套事件來源

- **Decision**: 平台管理員操作使用既有 `AuditRecord` 與 `AuditService`，`organization_id` 保持 null、`resource_type = platform`，以 operation id 關聯替換中的新舊兩筆狀態變更。成功與拒絕操作都保留事件；成功事件固定使用 `result = success`，拒絕事件固定使用 `result = denied`，拒絕原因使用安全且可理解的 domain code。
- **Rationale**: 既有 AuditRecord 已支援平台資源與 before／after／reason／result；沿用可讓平台操作與其他重要異動使用一致查詢與追溯模型。
- **Alternatives considered**: 新增 platform_admin_audit 表會產生無法與既有稽核入口對帳的第二事實來源；只記成功操作會遺失安全拒絕與嘗試資訊。

## Decision 6: 以明確操作契約區分啟用、停用、降權與替換

- **Decision**: API 以明確的建立／提升、啟用、停用、降權與替換操作表達意圖；不提供封存、硬刪除或移除 User。最後一位平台管理員的降權或停用拒絕；替換在單一交易內完成目標檢查與新舊角色異動。
- **Rationale**: 明確 action 比允許任意 PATCH role/status 更容易審查上下限、呈現確認訊息與建立精確稽核事件。
- **Alternatives considered**: 單一自由格式 PATCH 容易讓前端或其他 caller 繞過替換語意；hard delete 會破壞帳號、Session、Audit 與歷史關聯。

## Decision 7: 平台頁以治理摘要優先

- **Decision**: `/platform-admins` 頁首顯示目前啟用人數、最小／最大值、剩餘名額與主要操作；清單分為啟用中與已停用的平台管理員，降權或撤銷平台權限的歷史狀態透過平台稽核查詢；替換流程要求明確選擇新舊帳號並確認。
- **Rationale**: 管理者首先需要知道平台是否仍符合治理政策，再處理個別帳號；偏灰樣式延續既有權限管理頁的狀態辨識模式。降權會清除 `platform_role`，直接列入目前清單會混淆有效權限與歷史紀錄。
- **Alternatives considered**: 只顯示帳號卡片會讓上限與可用名額不明確；把平台管理員混在 Membership 卡片中會讓全域與收容所角色難以區分。
## Decision 8：明確定義帳號資格

- **決策**：新建、提升或替換的帳號必須使用非空且唯一的 username，且 User 必須為啟用狀態。
- 目標帳號不得已擁有 `PLATFORM_ADMIN`，避免同一 User 重複加入平台管理員集合。
- 新帳號的臨時密碼沿用既有密碼政策與雜湊流程，不新增第二套密碼實作，也不得以明文保存密碼。

## Decision 9：既有資料庫與空資料庫的 Migration 行為

- Migration 建立平台管理政策 singleton，並驗證目前啟用中的平台管理員人數。
- 已存在 User 資料的資料庫若平台管理員數量為 `0` 或大於 `2`，Migration 必須 fail-closed 並提供修復訊息，避免生產環境默默接受無效狀態。
- 空資料庫允許完成 Schema Migration；但在服務公開使用前，local 或 deployment bootstrap／seed 流程必須建立至少一名啟用中的平台管理員。

## Decision 10：排除所有具志工關聯的帳號

- **決策**：既有帳號提升候選清單必須排除具備任何 `VOLUNTEER` OrganizationMembership 或 VolunteerApplication 的 User，不論志工紀錄目前是啟用、過期、拒絕、撤銷或待處理狀態。提升與替換操作也必須在後端拒絕相同帳號。
- **理由**：志工歷史與待處理申請代表該帳號曾經或目前屬於志工流程。即使目前志工權限已失效，也不應將其顯示為平台管理員候選人，以避免不安全的角色轉換。
- **考量過的替代方案**：只篩選啟用中的志工 Membership 仍會讓過期、拒絕、撤銷紀錄及待處理申請重新出現在候選清單；依 display name 或 username 篩選則不可靠，也不能形成授權邊界。

## Decision 11：透過真實 Repository 驗證志工歷史限制

- **決策**：補強測試使用真實的 `PlatformAdminRepository` 與 `PlatformAdminManagementService`，並連接 PostgreSQL 測試資料庫。候選清單、提升與替換操作都必須使用已持久化的志工歷史資料驗證；每項測試在交易中執行，完成後 rollback fixture 資料。
- **理由**：既有 unit test 只能證明 Service 能處理 Repository 回傳的布林值，無法證明 Repository 能正確查出過期、撤銷、拒絕、撤回或待處理紀錄。Repository query 是安全邊界，必須直接驗證。
- **考量過的替代方案**：只擴充 fake Repository 的 unit test 雖然較快，但無法捕捉 query regression；只測試 UI 則無法驗證後端提升與替換的限制。

## Decision 12：撤銷 fixture 的定義不新增角色來源

- **決策**：撤銷 fixture 使用啟用中的 User，並建立 `role = VOLUNTEER`、`status = revoked` 的 `OrganizationMembership`。平台候選查詢持續透過既有的 `OrganizationMembership`／`VolunteerApplication` 存在性檢查排除該 User，不直接查詢 `VolunteerAccessGrant`，也不新增平台管理員或志工專用狀態欄位。
- **理由**：`revoked` 是志工權限的生命週期狀態，不是新的授權角色。測試應證明歷史志工身份仍會被排除，而不需改變 CRM 的資料來源。
- **考量過的替代方案**：只查詢目前的 `VolunteerAccessGrant.status`，會讓候選資格依賴衍生資料，可能使具志工歷史的帳號重新出現；新增平台專用排除旗標則會重複保存志工身份資料，違反既有角色分離原則。
