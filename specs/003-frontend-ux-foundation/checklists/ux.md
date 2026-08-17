# 需求品質檢查清單：前端體驗一致化與響應式 UI 基礎

**目的**：以 reviewer／作者視角檢查 UX 規格是否完整、清楚、一致且可驗收；本清單檢查需求文字品質，不檢查程式實作是否完成。
**建立日期**：2026-08-14
**功能**：[spec.md](../spec.md)

**範圍**：P0 核心流程、P1／P2 邊界、共用狀態、響應式、無障礙、權限與租戶隔離、原始資料保存、AI 人工覆核邊界，以及 FR／SC traceability。
**使用時機**：實作前的 spec／plan／tasks review；標記為 `[Gap]`、`[Ambiguity]` 或 `[Conflict]` 的項目需在進入實作前處理或留下明確決策。

## 需求完整性

- [ ] CHK001 是否已涵蓋 `/login`、管理首頁、Management Shell、動物、回報、Timeline、動物確認與照護回報等所有 P0 route 的使用者價值與主要任務？ [Completeness, Spec §頁面與路由 UX 目標]
- [ ] CHK002 是否已為工作人員、志工、收容所管理者與平台管理員分別說明主要任務、可見範圍與不可執行的操作？ [Completeness, Spec §使用者情境與驗收]
- [ ] CHK003 是否已完整定義 loading、saving、success、empty、no-results、error、permission-denied、processing、ai-failed 與 needs-review 的必要文案、下一步與資料保留規則？ [Completeness, Spec §UX 狀態規則; Gap]
- [ ] CHK004 是否已明確區分 P0、P1、P2 的交付內容、完成條件與相互依賴，並說明 P1／P2 未完成時 P0 仍可獨立驗收？ [Completeness, Spec §交付範圍]

## 需求清晰度

- [ ] CHK005 「目前收容所」、「目前頁面」、「主要操作」與「可用管理範圍」是否都有足以讓不同 reviewer 得出相同判斷的定義？ [Clarity, Spec §FR-001～FR-004]
- [ ] CHK006 `saving`、`success`、`processing`、`ai-failed` 與 `needs-review` 是否使用同一套 canonical 名稱，且沒有以 `completed`、`saved` 或其他近義詞造成狀態漂移？ [Clarity, Spec §FR-010、FR-025; Data Model §UIStatusState]
- [ ] CHK007 「清楚」、「容易找到」、「合理焦點順序」、「適當下一步」等詞是否已由可觀察條件、內容要求或量化門檻補足？ [Clarity, Spec §FR-001、FR-015、FR-021、FR-033]
- [ ] CHK008 Drawer 作為產品互動語意、Sheet 作為手機對應、Dialog 作為一般內容視窗、AlertDialog 作為高風險確認的邊界是否前後一致？ [Clarity, Spec §Overlay 語意; Contract §5]

## 需求一致性

- [ ] CHK009 P0 gate 是否明確不需要 P1／P2 的 spec、browser evidence、script 或資料輸出？ [Conflict, Constitution §IX; Plan §交付層級定義]
- [ ] CHK010 SC-007 的 P0 evidence 是否與 P1 extension evidence 分離，避免 T054／T055 被解讀為 P0 完成必要條件？ [Conflict, Plan §FR／SC 追溯矩陣]
- [ ] CHK011 `saving` 是否在 spec、data-model、UI contract、plan 與 tasks 中具有一致的狀態名稱、轉換、輸入保留與 live-region 語意？ [Consistency, Gap]
- [ ] CHK012 quickstart、plan route matrix 與 US5 acceptance 是否列出相同的 P0 routes，包含 `/login`、管理首頁、detail pages 與四組 viewport？ [Consistency, Spec §SC-003; Plan §瀏覽器證據]
- [ ] CHK013 AI 狀態呈現是否與「AI 不負責最終判定」、「原始資料不得被衍生結果取代」及「AI 失敗不阻止人工流程」保持一致？ [Consistency, Constitution §II～IV; Spec §FR-010、FR-025]

## 驗收條件品質

- [ ] CHK014 SC-001 是否明確定義任務起點、完成點、90 秒計時範圍、代表性志工樣本與 90% 判定方式？ [Acceptance Criteria, Spec §SC-001; Plan §可用性指標執行規範]
- [ ] CHK015 SC-002 是否明確定義管理首頁起點、目標頁面完成點、30 秒計時範圍、代表性工作人員樣本與 90% 判定方式？ [Acceptance Criteria, Spec §SC-002; Plan §可用性指標執行規範]
- [ ] CHK016 SC-003 是否明確定義 360px、768px、1024px 與桌面寬度下「不可讀、重疊、截斷與不必要水平捲動」的判定方式？ [Measurability, Spec §SC-003、FR-026～FR-030]
- [ ] CHK017 SC-004 是否涵蓋所有核心操作，而不只包含導覽與 focus，並清楚說明表單修正、保存、返回、錯誤重試與 overlay 操作的完成條件？ [Completeness, Spec §SC-004、FR-033～FR-034]
- [ ] CHK018 SC-005 是否對每一種狀態定義可理解的繁體中文訊息、下一步、aria/live-region 期待與不可混淆的相鄰狀態？ [Measurability, Spec §SC-005、FR-019～FR-025]
- [ ] CHK019 SC-006 與 WCAG 2.2 AA 導向是否明確涵蓋鍵盤、focus、欄位關聯、Dialog／Sheet、icon-only 控制與螢幕閱讀器語意？ [Completeness, Spec §SC-006、FR-032～FR-037]

## 情境覆蓋

- [ ] CHK020 管理 Shell 的主要、替代與復原情境是否都定義了有效 context、無 context、context 切換成功、切換失敗、登出與 session 失效的需求？ [Coverage, Spec §使用者故事 1、FR-004、FR-006]
- [ ] CHK021 志工流程是否同時涵蓋今日名單、QR Code、收容編號搜尋、確認、重新選擇、草稿恢復、保存成功與保存失敗？ [Coverage, Spec §使用者故事 2、FR-007～FR-012]
- [ ] CHK022 管理核心是否涵蓋搜尋、篩選、分頁、日期變更、返回脈絡、detail、Timeline、同日多筆與歷史 snapshot？ [Coverage, Spec §使用者故事 3、FR-013～FR-018]
- [ ] CHK023 AI 情境是否明確區分原始回報已保存、AI processing、AI failed、需要人工覆核與人工決定完成，且沒有把 AI 失敗寫成資料保存失敗？ [Coverage, Constitution §II～IV; Spec §FR-010、FR-025]
- [ ] CHK024 P1 頁面是否都有一致的權限、狀態、響應式與 tenant scope 需求，且其驗收內容不會反向成為 P0 必要條件？ [Coverage, Spec §使用者故事 6、FR-044]

## 邊界情況

- [ ] CHK025 是否已定義相同 shelter number、相近名稱、無可用 shelter、單一 shelter、無可回報動物與只有停用資料時的安全且可理解需求？ [Edge Case, Constitution §XI; Spec §邊界情況]
- [ ] CHK026 是否已定義快速變更搜尋條件、過期 response、日期範圍不完整與資料在查詢期間被更新時的結果一致性需求？ [Edge Case, Spec §邊界情況、FR-018]
- [ ] CHK027 是否已定義瀏覽器返回、重新整理、深連結、網路中斷、保存衝突、重複提交與 AI timeout 的復原需求？ [Recovery, Spec §邊界情況、FR-009、FR-012、FR-023、FR-042]

## 非功能需求

- [ ] CHK028 響應式需求是否同時涵蓋長中文、放大文字、44px touch target、表格轉卡片／展開內容、sticky layout 與無 hover 情境？ [Completeness, Spec §FR-026～FR-031; Plan §響應式規則]
- [ ] CHK029 無障礙需求是否明確說明 focus visible、focus trap、focus restore、Escape、錯誤關聯、live region、reduced motion 與 icon-only accessible name？ [Completeness, Spec §FR-032～FR-037; Contract §9]
- [ ] CHK030 權限與租戶隔離需求是否明確指出前端隱藏或 disabled 不是安全邊界，且後端已驗證 context 才是資料範圍來源？ [Security, Constitution §VIII、XI; Spec §FR-003、FR-040、FR-041]
- [ ] CHK031 CRM 唯一事實來源、原始文字／照片／表單值、歷史 snapshot、AI raw output、人工修正與稽核追溯是否都有不可被 UI migration 改變的明確需求？ [Completeness, Constitution §I、II、IV、VI; Spec §FR-038、FR-039、FR-043、FR-044]
- [ ] CHK032 後端冪等性／唯一性保護失敗時，是否明確定義 P0 gate 必須 blocked，且不能由 pending、disabled、UI test 或 visual evidence 取代？ [Security, Constitution §VII、IX; Spec §FR-012; Plan §P0 gate 判定]

## 依賴、假設與追溯

- [ ] CHK033 代表性 seed、角色帳號、ORG-A／ORG-B tenant fixture、同日多筆回報、AI failure 與保存錯誤是否被列為可取得且可驗證的前置條件？ [Dependency, Spec §假設; Quickstart §前置條件]
- [ ] CHK034 usability sample 不足、可靠 timestamp 不存在、測試資料不完整或協助介入時，是否明確規定 preliminary、分母與補測責任？ [Assumption, Spec §假設; Plan §可用性指標執行規範]
- [ ] CHK035 每一個 FR 與 buildable SC 是否都有不依賴 P1 的任務或 evidence 對應，且 traceability matrix 不把 post-launch KPI 當成 P0 build gate？ [Traceability, Plan §FR／SC 追溯矩陣]

## 歧義與衝突

- [ ] CHK036 「桌面寬度」、「合理 max width」、「可辨識名稱」與「適合的下一步」是否已被具體化到不同 reviewer 能一致判斷？ [Ambiguity, Spec §FR-002、FR-021、FR-026]
- [ ] CHK037 P0 收尾任務是否沒有要求 P1 scripts 或 P1 spec 存在，且 P1 tooling verification 已明確放在 US6 或 P0 之後？ [Conflict, Constitution §IX; Tasks §階段 8、階段 9]
- [ ] CHK038 `StatusView`、`EmptyState`、`ErrorState`、`StatusBanner`、Alert、Toast 與 Sheet 是否各自有唯一語意，沒有讓同一狀態或 Drawer 行為出現多套互相競爭的需求？ [Ambiguity, Plan §統一狀態與 overlay 對照; Contract §5、§7]

## Notes

- 本清單的項目是需求品質問題，不是程式、browser、axe 或手動驗收步驟。
- `P0 gate`、`saving`、SC-007 evidence 分離與完整 P0 route matrix 是目前優先需要釐清的項目。
- 建議在 P0/P1 邊界、`saving` 狀態、後端冪等性 gate 與 P1 tooling 依賴尚未釐清前，不宣稱規格已達到可安全實作狀態。
