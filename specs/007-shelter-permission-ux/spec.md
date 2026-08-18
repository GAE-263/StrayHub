# Feature Specification: 收容所權限管理介面改善

**Feature Branch**: `007-shelter-permission-ux`

**Created**: 2026-08-17

**Status**: Ready for planning

**Input**: User description: "改善收容所管理員在 /shelters 的權限管理介面：頁面標題使用「權限管理」；Membership 清單不可只顯示難以辨識的 user UUID，應顯示使用者姓名與帳號；會員角色、狀態、醫療資料權限與停用操作要有清楚分層且不擁擠的排版；所有台灣各地收容所統一使用 Asia/Taipei，不需要在此頁修改時區。以 local-shelter-admin-a 身份驗證，現有帳號與 Membership、角色狀態、STAFF 醫療資料權限與既有管理操作都必須保留。"

## User Scenarios & Testing _(mandatory)_

### User Story 1 - 辨識收容所帳號與權限 (Priority: P1)

收容所管理員開啟權限管理頁面時，可以用使用者姓名與帳號辨識每一筆 Membership，不必從 UUID 猜測操作對象；同時可以清楚看到角色、Membership 狀態，以及 STAFF 是否具備醫療資料權限。

**Why this priority**: 這是管理員安全執行停用或調整角色前的必要資訊，直接降低誤操作風險。

**Independent Test**: 以 `local-shelter-admin-a` 登入 A 收容所，開啟 `/shelters`，確認清單以姓名／帳號呈現五筆以上既有 Membership，並能對照角色、狀態與 STAFF 醫療權限；畫面不以 UUID 作為主要識別。

**Acceptance Scenarios**:

1. **Given** A 收容所存在 STAFF、VOLUNTEER 與 SHELTER_ADMIN Membership，**When** 管理員開啟權限管理頁面，**Then** 每筆清單顯示可辨識的顯示名稱，並在有帳號時顯示帳號名稱。
2. **Given** 清單同時包含 active、disabled、expired 或 revoked 狀態，**When** 管理員查看清單，**Then** 每筆狀態均以清楚的文字標籤呈現，不以顏色作為唯一資訊。
3. **Given** 某筆 Membership 的角色是 STAFF，**When** 管理員查看該筆資料，**Then** 可以辨識醫療資料權限是否啟用；非 STAFF 角色不顯示不適用的醫療權限控制。

---

### User Story 2 - 以不擁擠的版面管理權限 (Priority: P1)

收容所管理員可以在桌面與手機寬度下，分辨帳號資料、角色／狀態摘要與可執行操作；每筆 Membership 的操作不會與其他欄位重疊或擠在難以閱讀的單行排列中。

**Why this priority**: 權限管理是高風險操作，清楚的資訊層級與可點擊區域能降低誤選角色、誤停用帳號或漏看權限狀態的機會。

**Independent Test**: 在 1440px、768px 與 360px 寬度開啟頁面，確認每筆 Membership 的姓名、帳號、角色、狀態、醫療權限與停用操作均可閱讀、可操作且不發生水平溢出或重疊。

**Acceptance Scenarios**:

1. **Given** 清單有多筆 Membership，**When** 管理員使用桌面寬度查看，**Then** 每筆資料以視覺分隔的區塊呈現，身份資訊、狀態摘要與操作區域具有清楚間距。
2. **Given** 管理員使用手機寬度查看，**When** 管理員操作角色、醫療權限或停用帳號，**Then** 控制項會依可用寬度重新排列，仍保持完整文字與足夠的操作尺寸。
3. **Given** 頁面載入或操作失敗，**When** 管理員查看錯誤訊息，**Then** 錯誤訊息不會破壞 Membership 清單的排列或遮住操作控制。

---

### User Story 3 - 使用固定的台灣收容所時區 (Priority: P2)

收容所管理員查看權限管理頁面時，知道所有台灣各地收容所使用 Asia/Taipei（台灣時間），但不需要在此頁維護時區選項或儲存時區變更。

**Why this priority**: 目前服務對象都是台灣各地收容所，移除不必要的設定可降低管理負擔並避免誤改日期計算依據。

**Independent Test**: 以收容所管理員開啟權限管理頁面，確認頁面說明統一使用 Asia/Taipei，且不顯示時區選擇器或儲存時區操作；既有帳號與 Membership 管理仍可使用。

**Acceptance Scenarios**:

1. **Given** 收容所管理員開啟權限管理頁面，**When** 查看收容所資訊，**Then** 頁面顯示所有台灣收容所統一使用 Asia/Taipei（台灣時間）的說明。
2. **Given** 頁面已載入，**When** 管理員尋找時區設定，**Then** 不會看到可切換其他時區的選單或儲存時區按鈕。
3. **Given** 管理員執行角色調整、醫療權限調整或帳號停用，**When** 操作完成，**Then** 既有權限與稽核行為維持不變。

### Edge Cases

- 使用者沒有顯示名稱但有帳號時，頁面以帳號作為主要識別；兩者皆缺少時，頁面顯示安全的未命名提示，不把 UUID 當作主要名稱。
- Membership 清單含有過期或撤銷的志工時，狀態仍須可辨識，且不應誤顯示為啟用中。
- STAFF 的醫療資料權限未啟用時，管理員仍可辨識「停用」狀態；非 STAFF 不應出現醫療權限切換控制。
- 權限管理員在不同視窗寬度重新載入頁面時，清單資料、角色與狀態不得因排版變更而遺失。
- 使用者資料查詢失敗時，頁面不得以隨機或跨收容所資料補上姓名；應顯示安全的未命名提示並保留其他權限資訊。

## Requirements _(mandatory)_

### Functional Requirements

- **FR-001**: 權限管理頁面的主要標題 MUST 顯示「權限管理」。
- **FR-002**: Membership 清單 MUST 顯示每筆成員的顯示名稱；有帳號名稱時 MUST 同時顯示帳號名稱。
- **FR-003**: Membership 清單 MUST NOT 以 `user_id` UUID 作為主要可見身份名稱；UUID MAY 保留在非主要的技術識別或操作關聯中。
- **FR-004**: 每筆 Membership MUST 清楚呈現角色與狀態文字，至少支援 SHELTER_ADMIN、STAFF、VOLUNTEER 以及 active、disabled、expired、revoked 等既有狀態。
- **FR-005**: STAFF Membership MUST 提供醫療資料權限的目前狀態與既有切換操作；非 STAFF Membership MUST 不顯示不適用的醫療資料權限控制。
- **FR-006**: 既有 Membership 角色調整、醫療資料權限調整、帳號停用、錯誤回饋與稽核行為 MUST 維持原有授權邊界與結果。
- **FR-007**: 權限管理頁面 MUST 在桌面與手機寬度下以分層區塊呈現身份、狀態與操作，且不得造成文字、控制項重疊或不可操作。
- **FR-008**: 權限管理頁面 MUST 說明台灣各地收容所統一使用 `Asia/Taipei`（台灣時間）。
- **FR-009**: 權限管理頁面 MUST NOT 提供時區選擇器、其他時區選項或儲存時區按鈕。
- **FR-010**: Membership 清單取得的使用者姓名與帳號資料 MUST 受目前已驗證的收容所管理範圍限制，不得因顯示名稱需求洩漏其他收容所使用者資料。
- **FR-011**: 使用者識別資料缺少或取得失敗時，頁面 MUST 使用安全的未命名提示，且不得以跨收容所或未驗證來源的資料填補。

### Key Entities _(include if feature involves data)_

- **使用者**：具備顯示名稱與帳號名稱的登入主體，僅在目前已驗證收容所管理範圍內提供給權限管理清單辨識。
- **Membership**：使用者與收容所的角色關聯，包含角色、狀態與 STAFF 的醫療資料權限狀態。
- **收容所設定**：目前收容所的識別資訊與固定台灣時區說明；本功能不提供時區變更。

## Success Criteria _(mandatory)_

### Measurable Outcomes

- **SC-001**: 管理員在 10 秒內可從清單辨識任一既有 Membership 的姓名或帳號、角色與狀態，不需要複製或比對 UUID。
- **SC-002**: 在 1440px、768px 與 360px 三種寬度下，100% 的 Membership 清單項目都沒有文字或控制項重疊，且所有既有操作仍可觸發。
- **SC-003**: 以 `local-shelter-admin-a` 驗證時，清單至少五筆既有 Membership 均能顯示可辨識使用者資訊；其中 STAFF 的醫療權限狀態與 active／expired 狀態均正確呈現。
- **SC-004**: 權限管理頁面不再提供任何可修改時區的控制項，且 100% 的台灣收容所頁面顯示 Asia/Taipei 統一使用說明。
- **SC-005**: 既有角色調整、醫療資料權限切換與停用帳號流程的成功與拒絕結果，與功能改善前保持一致，且每次成功異動仍可追溯操作者與結果。

## Assumptions

- 現有登入、Active Shelter Context、Membership 授權與稽核流程沿用，不在本功能重新設計。
- 使用者資料已有可靠的顯示名稱與帳號欄位；本功能只補足管理清單所需的辨識資訊，不建立第二份使用者資料。
- 第一階段只處理目前 `/shelters` 權限管理頁面，不改動其他管理頁的時區顯示或帳號呈現。
- 手機版只要求內容可讀與可操作，不新增專用原生 App 或離線能力。
- 使用者未提供第 5 點內容，因此本規格不新增其他需求。
