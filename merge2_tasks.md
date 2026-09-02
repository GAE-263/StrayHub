# Emily Walk Report Integration Tasks

本文件定義如何把 Emily 的志工散步回報功能安全整合到 StrayHub
`5b9831f95f4c11bd13e706071ad32979611fd880`（`feat(web): add QR management search and
pagination`）。主要行為參考是 Emily 的 `9e534ebd` 及其 earlier commits，但 integration
必須以 `5b9831f` 的 multi-shelter、authorization、QR management、role-based LINE menu、
adoption routing 與 worker 架構為準。LINE Bot的in-chat UI、Flex presentation、視覺層級、
互動文案與回饋節奏則以Emily branch的最終產品版本為主要設計source。

這是一份執行計畫，不代表任何 Phase 已獲准開始。人工確認本文件以前，禁止實作、建立
migration、修改 tests、cherry-pick、commit 或 push。

## 0. Integration Principles

1. **固定 baseline**：integration branch 必須從 exact `5b9831f95f4c11bd13e706071ad32979611fd880`
   建立。開始前重新驗證 SHA，不以會移動的 branch name 代替。
2. **Semantic port only**：不可 rebase Emily entire branch、不可批次 cherry-pick、不可
   cherry-pick `b1f8bd8`。每個 Emily commit 只作 behavior/dependency reference。
3. **Current architecture wins**：發生衝突時，以 `5b9831f` 的 authentication、authorization、
   tenant scope、adoption flow、role menu、QR management、worker 與 migration chain 為準。
4. **Emily LINE Bot UI wins**：不涉及安全、authorization、routing architecture或已凍結產品IA的
   presentation決策，以Emily在`9e534ebd`的最終in-chat UI為主，不自行改回baseline的plain
   quick-reply/template UI，也不另做新的視覺語言。歷史commit只用來理解演進，不能把舊13題文案帶回。
5. **Multi-shelter 是安全邊界**：animal search、QR resolve、today list、confirmation、draft、
   report、media、AI job、AI observation 與 timeline 都必須由 server-resolved current
   organization 限定。client/postback/QR payload 不能成為 organization authorization source。
6. **QR 只是 locator**：QR 找到 animal 後必須進共用 Animal Confirmation；不能直接建立
   draft 或開始回報。
7. **Report 與 draft 不混用**：submitted report 是不可變的歷史紀錄；只有 active draft
   代表未完成工作並參與 resume/switch。
8. **AI 是 asynchronous enhancement**：CareReport persistence 是 primary path；AI enqueue、
   provider、worker 或 observation persistence 失敗不得讓正式回報失敗或消失。
9. **Phase isolation**：Phase 1–5 各自完成 code、targeted tests、diff review 與 dedicated local
   commit 後，才可進下一個 Phase。不得把多個 Phase 混在一顆 commit。
10. **No push**：本計畫只允許 local commits。push、PR、deploy 需要另外授權。
11. **Hard stop**：任何 cross-shelter exposure、multiple Alembic heads、adoption routing regression、
    LINE signature/idempotency regression，或無法解釋的 baseline failure 都必須停止下一 Phase。

## 1. Canonical Product Decisions

### 1.1 Entry and find-animal flow

```text
主選單
→ 志工服務
→ 散步回報
→ 找動物
   ├─ 掃描 QR
   ├─ 搜尋動物
   └─ 今日名單
```

三種找動物方式都是正式功能。人工搜尋至少支援 animal name 與 shelter number 的 partial
match；多筆結果必須顯示 candidates 讓志工選擇，禁止自動猜測。結果超過 LINE/API 單頁容量時
必須 pagination，不得 silent truncation。

QR、search、today list 最後都進同一個 Animal Confirmation。Confirmation 至少顯示：

- animal name
- shelter number
- area/location
- photo（若存在）
- current shelter
- 「確認這隻動物」
- 「重新選擇」

### 1.2 Canonical six-question state sequence

題目、順序與選項文案全部凍結，不得自行精簡、同義改寫或恢復舊 13 題：

```text
1. 散步完成
   - 有走完
   - 走一半
   - 沒走成

2. 精神體力
   - 比平常好
   - 跟平常一樣
   - 比平常差

3. 走路姿勢
   - 正常
   - 有點怪
   - 明顯不對

4. 大便
   - 正常
   - 偏軟
   - 沒排便
   - 有異狀

   沒排便 / UNOBSERVED
   → 跳過便便照片

   正常 / 偏軟 / 有異狀
   → 詢問便便照片
   → 可上傳，也可略過

5. 對其他狗
   - 友善
   - 沒反應
   - 緊張或想衝
   - 路上沒遇到

6. 身體外觀
   - 沒發現異狀
   - 皮膚或毛髮異常
   - 傷口或紅腫
   - 其他

→ note
→ story
→ review
→ submit
```

Stool-photo step 必須保留在第 4 題後、進入第 5 題前。正常便便也必須詢問照片。不可把
stool photo 移到第 6 題後，也不可改成只有異常才詢問。

### 1.3 UNOBSERVED

`UNOBSERVED` 的使用者文案是「今天沒觀察到這項」。它是 Bot/domain sentinel，不是 CRM
observation option：

```text
UNOBSERVED != 正常
UNOBSERVED != 沒發生
大便 = 沒排便    → 有觀察，確認沒有排便
大便 = UNOBSERVED → 沒有足夠觀察資料
```

可以為 UNOBSERVED 保存歷史顯示 representation/snapshot，但不得把它建立成 vocabulary option，
也不得計入 observation option usage。

### 1.4 Note, story, required-note and history

- `note` 是健康／行為補充。
- `story` 是今日有趣的小故事，用於 adoption/social storytelling。
- 兩者不可合併，也不可在切換 animal 時沿用。
- 任一已選 observation option 若 `requires_note`，note step 不得顯示或接受誤導性的 skip。
- answer snapshots 必須保存送出當下的 label/description，未來 vocabulary 改名不能改寫歷史。
- 同一 animal 同一天允許多筆 submitted walk reports，不得增加 `animal_id + date` unique constraint。

### 1.5 Today List and draft safety

Today List 分成「尚未回報」與「今日已回報」。已回報 animal 仍可點擊並再次建立新回報；應顯示
今日回報次數與最近一次 local time。

Active draft selection rules：

```text
沒有 active draft → 正常選擇並建立 draft
同一 animal       → resume existing draft
不同 animal       → warning → explicit confirmation → switch
```

切換 animal 不得殘留 media、note、story，或任何無法安全沿用的 answers/context。不得 silent
reassignment。

### 1.6 Authorization and command

Volunteer walk-report authorization 使用：

```text
LINE identity
+ server-confirmed active organization
+ valid active volunteer membership/access grant
+ VolunteerReportingAuthorizationService（或 current equivalent）
```

不得重新把 `DailyReportableScope` 當第二套 allow-list。若 current selection/submission/webhook
仍使用 DailyScope，這是本 integration 必須 reconcile 的 semantic debt。

產品 command 固定為「開始散步回報」。LIFF sendMessages、manual fallback copy、webhook exact
matcher、fixtures/tests 必須同步；exact system command routing 必須早於 note、story 或 generic
free-text capture。

### 1.7 Explicit scope boundary

```text
OUT OF SCOPE — Volunteer Check-in
```

現有「志工報到」placeholder 必須 leave untouched：不修改、不實作、不刪除、不新增 attendance
model/API/routing、不作為 walk-report prerequisite，也不納入 acceptance criteria。

### 1.8 LINE Bot UI design source of truth

LINE Bot的in-chat UI以Emily在`9e534ebd`所呈現的最終版本為主，尤其包含：

- Flex Message的block/sticker視覺語言、色彩角色、卡片層級與可讀性。
- find-dog hub、question cards、stool-photo prompt、note/story prompt、required-note warning、
  confirmation、review summary、success/celebration、error與empty-state feedback。
- button label、提示文案、資訊揭露順序、分頁/繼續操作的interaction rhythm。
- animal confirmation中重要識別資料的清楚呈現，不能退回只靠plain text猜測的UI。

實作時先從Emily final branch與`6374592`的最終presenter/tests建立UI contract，再適配Phase 2的
current application results與Phase 3的current webhook。不得用baseline較陽春的quick reply當作設計
source，也不得由implementation agent自行重新設計。

此優先序不允許覆蓋下列邊界：

- current role-based Rich Menu IA、Main/Volunteer/Adoption navigation與Volunteer Check-in placeholder。
- current adoption presenter/routing、安全檢查、LINE平台格式限制與accessibility/readability要求。
- canonical六題文案、Q4 stool順序、authorization與tenant isolation。

若需要更新Rich Menu圖片，只能把Emily的視覺語言適配到current IA；不得恢復Emily舊的
「開始／繼續／聯絡工作人員」單一三格navigation layout。

## 2. Known Integration Risks

| Risk | Evidence at `5b9831f` | Required mitigation |
|---|---|---|
| Authorization split | `AnimalSelectionService` 已使用 `VolunteerReportingAuthorizationService`，但 LINE draft submission 與部分 report path 仍查 `ReportableScopeRepository` | Phase 1 不新增 DailyScope dependency並保留與core domain無關的current行為；Phase 2才實際移除walk-report path的第二套allow-list，並在submission前重新驗證current membership/grant/animal |
| Webhook semantic overwrite | Emily webhook 早於 current adoption、role menu、idempotency 與 QR management | 只手動 port小段行為；不得整檔採 Emily version |
| UI design drift | baseline LINE訊息較陽春，implementation agent可能自行簡化或重新設計Emily Flex UI | 先凍結Emily final UI contract；presentation以`9e534ebd`/`6374592`為主，只適配current services與routing |
| Migration collision | Emily 曾使用 `0031`/`0036`；baseline 已到 `0038_line_adoption` | implementation 當下跑 `alembic heads` 後建立 current head 的新 child，不預寫 revision number |
| Worker overwrite | current worker 有 volunteer-access loop；Emily worker增加 AI loop | 保留 current loop，新增 bounded AI iteration；不可替換 worker entry point |
| Draft data leakage | baseline reselection會清 media，但未完整清 note/story/context | switch transaction中明確清理並以 tests證明 |
| Today List wrong semantics | Emily 使用 DailyScope，且只記 latest time | 使用 current authorization與 org-scoped report aggregate，回傳 count + latest 並分兩組 |
| Command swallowed as text | baseline使用「開始照護回報」且文字可能落入 note | 一次同步 protocol surfaces並先 route exact command |
| Image ambiguity | QR image、stool image與 generic image可能進同一 webhook branch | Phase 3 依 server-side draft/state/entry intent dispatch，未知狀態拒絕 |
| Adoption regression | active adoption text/postback已存在 | 保留 adoption flow-specific routing；新增雙向 isolation tests |
| AI blocks primary path | provider/network/job failures | report先 commit；dispatch/worker失敗只能更新 AI status，不得回滾 report |
| Timeline cross-org/read ordering | `9e534ebd` 主要依 report IDs與 observation org filter，latest只按 `created_at` | 同時 filter job/observation org，使用 `created_at, id` deterministic ordering並加 repository tests |
| Clean patch false confidence | `9e534ebd` 五檔 patch可套到 baseline | 仍延後到 Phase 5，待 media/runner/provider/observation chain 完成 |

## 3. Emily Commit Mapping

| Commit | Behavior reference | Decision |
|---|---|---|
| `483cbbf` | LINE data host/error logging | baseline已有等價行為，不 port |
| `c595397` | Flex UI早期基礎（內容仍是舊13題） | 只作UI演進reference；不可port其題目/文案，最終UI以`6374592`與`9e534ebd`為準 |
| `b497e77`, `029a340`, `3f3457c`, `4170355`, `d48800a`, `6a97bfc`, `2dd3ad3` | 歷史文件 | 不直接 port；完成後依 current architecture更新必要文件 |
| `46c5120`, `62e42e6`, `4fe780b`, `61298c2` | 舊 formatting/ignore/test cleanup/script workaround | obsolete或 out of scope |
| `71cebe0` | AIJobRunner、claim/retry/worker iteration | Phase 4 手動適配 current worker |
| `73874c3` | 舊 vocabulary display names | 由 frozen canonical wording取代 |
| `b6e932c` | Rich Menu image Content-Type | Phase 3 檢查 baseline後只補 missing hardening |
| `3d11d45`, `76ea523` | required-note UX、人類可讀文案 | Phase 1 domain rule；Phase 3 presenter delivery |
| `1d8082f` | LINE snapshots/usage wiring | Phase 1 手動 port到 current submission service |
| `3ee3c41` | LINE candidate pagination | Phase 2 做資料/分頁模型，Phase 3 接 LINE delivery；不得帶 DailyScope |
| `7b3d515` | Today overview/latest time | Phase 2 重做 count/latest/sections；不得帶 DailyScope |
| `33f9023` | 6 題、stool media、story | Phase 1 核心 reference；不可整顆 cherry-pick |
| `6374592` | 最終 Flex block/sticker與可讀性 | Phase 3 LINE Bot UI主要design source；適配current routing但不可覆蓋adoption presenter |
| `f2b750b` | same-animal resume、different-animal warning | Phase 2 service behavior reference |
| `f90a7b7` | `tzdata` dependency | Phase 2 實作 timezone需求時以 `uv` 更新 current lock |
| `60d4fa4` | 舊 migration dependency fix | obsolete；禁止 port |
| `3b1258d` | exact command precedence | Phase 3 改用「開始散步回報」手動實作 |
| `b1f8bd8` | merge conflicts/auth drift/handoff limitation | knowledge only；禁止 cherry-pick |
| `49327a9` | stool provider、raw/formal output | Phase 4 手動適配 |
| `9e534ebd` | Timeline stool lookup/API/mapping/render | Phase 5 selective behavior reference |
| `af1c80c` | PowerShell demo helper | out of scope |

## 4. Current Baseline Compatibility

| Component | Baseline state | Planned action |
|---|---|---|
| `line_webhook` | 有 signature、event idempotency、adoption、role menu；walk routing仍舊 | Phase 3 surgical integration |
| `line_draft_conversation` | 13 題，無 stool/story/UNOBSERVED，submission仍查 DailyScope | Phase 1 state/submission；Phase 2 auth reconciliation |
| `AnimalSelectionService` | search/QR/confirm均 org-scoped，volunteer使用 current authorization | Phase 2 reuse，不恢復舊 signature |
| `VolunteerReportingAuthorizationService` | 驗證 user/org/membership/grant/animal | 作為 walk-report source of truth |
| `CareReportDraft` | 有 candidate/reconfirmation/note；缺 story | Phase 1 schema/model |
| `CareReport` | 有 snapshots、note、idempotency；缺 story；允許同日多筆 | Phase 1 schema/submission並保留多筆語意 |
| `MediaAsset` | 有 purpose；缺 subject | Phase 1 增加 nullable subject |
| Vocabulary | 舊 13 題 | Phase 1 換成 frozen六題，不把 UNOBSERVED建成 option |
| Worker | volunteer-access loop存在；AI runner未接 | Phase 4 additive integration |
| `AIProcessingJob` | 可支援 target/version/claim fields | Phase 4 reuse |
| `AIObservation` | raw/validated/human-review JSON相容 | Phase 4/5 reuse |
| `TimelineRepository` | report/media tenant-scoped；缺 stool lookup | Phase 5 additive query |
| `AnimalTimeline` | 可顯示 report/media/status；缺 stool analysis | Phase 5 types/mapping/render |
| Rich Menu | Main IA正確；Volunteer含 walk/check-in/back，walk仍placeholder | Phase 3只接 walk/back；check-in untouched |
| LIFF | confirmation與handoff UI存在；trigger仍是舊 literal | Phase 3同步 literal；handoff consumer deferred |

## 5. Phase 0 — Baseline Gate

**Purpose**：建立可重現、安全、未開始 implementation 的 integration baseline。

### P0-T01 — Verify exact source and clean worktree

- Likely components: Git only；不得修改 application files。
- Actions:
  - 執行 `git status --short --branch`，要求沒有未解釋變更。
  - 執行 `git rev-parse HEAD` 與 `git show -s --format='%H %s' 5b9831f`。
  - 確認 baseline完整 SHA為 `5b9831f95f4c11bd13e706071ad32979611fd880`。
  - 若 source moved或工作樹不乾淨，停止並由人工決定，不得 reset/discard使用者變更。
- Acceptance: exact SHA與clean status均已記錄。

### P0-T02 — Create the integration branch only after human authorization

- Action: 從 exact SHA 建立專用 branch，例如
  `git switch -c codex/emily-walk-report-integration 5b9831f`。
- Non-goal: 不得在同一步開始 Phase 1，不得 cherry-pick Emily commit。
- Acceptance: `git rev-parse HEAD`仍為 exact baseline；branch沒有額外 diff。

### P0-T03 — Verify migration topology

- Likely components: `services/api/migrations/versions/`, Alembic config。
- Actions:
  - 執行 repository既有的 `uv run alembic heads`（使用安全的 local/test DB設定）。
  - inspect `0035_care_report_handoffs → 0036_animal_profile → 0037_animal_external_sources →
    0038_line_adoption` 的 `revision/down_revision`。
  - 記錄實際 single head；若 multiple heads則停止，不得先建立 walk-report migration。
- Acceptance: current head與chain有證據，沒有 unresolved multiple heads。

### P0-T04 — Establish baseline tests

- Backend targeted baseline:
  - `uv run pytest tests/unit/test_line_care_report_state_machine.py`
  - `uv run pytest tests/unit/test_line_draft_conversation.py`
  - `uv run pytest tests/integration/test_line_postback_flow.py`
  - `uv run pytest tests/integration/test_multiple_care_reports.py`
  - `uv run pytest tests/integration/test_scope_free_animal_selection_api.py`
  - `uv run pytest tests/unit/test_volunteer_reporting_authorization.py`
  - `uv run pytest tests/integration/test_adoption_webhook_flow.py`
  - `uv run pytest tests/integration/test_qr_management_list.py`
  - `uv run pytest tests/integration/test_animal_timeline.py`
- Listed paths are baseline references, not permission to create or rename tests。若某個列出的test path在
  exact `5b9831f` 不存在，必須先用repository search（優先 `rg --files tests` 與 `rg`）找出當時的
  current equivalent test，記錄原列路徑、resolved equivalent path與判定理由，再執行該等價測試。
  Phase 0不得因path不存在就誤報baseline failure，也不得建立、rename或修改tests。
- Frontend baseline:
  - `npm --prefix apps/web run test`
  - `npm --prefix apps/web run typecheck`
- Quality baseline:
  - `uv run ruff check` on relevant current files, or `uv run ruff check .` if time permits。
  - `git diff --check`。
- Record every pre-existing failure separately with command/output summary。不得修改 test來掩蓋 baseline failure。
- Stop Gate 0: SHA、clean worktree、single Alembic head與baseline evidence全部完成後停止；等待人工授權 Phase 1。

## 6. Phase 1 — Walk Report Core Domain

**Dependency**：Phase 0 PASS。**Scope**：schema、model、state machine、submission semantics；不做
find-dog delivery、Rich Menu或AI。Phase 1不得引入任何新的`DailyReportableScope`／
`ReportableScopeRepository`依賴；對與core domain work無關的既有authorization行為保持不變。
Walk-report authorization reconciliation與第二套allow-list移除只屬於Phase 2。

- [x] P1-T01 — Add the minimum schema from the current Alembic head
- [x] P1-T02 — Replace the 13-question state machine with the frozen six-question flow
- [x] P1-T03 — Seed/effective vocabulary and UNOBSERVED representation
- [x] P1-T04 — Implement note, story and required-note semantics
- [x] P1-T05 — Wire answer snapshots and option usage for LINE submission
- [x] P1-T06 — Preserve multiple reports per animal/day

### P1-T01 — Add the minimum schema from the current Alembic head

- Likely files: `services/api/migrations/versions/`, `care_report_draft.py`, `care_report.py`。
- Actions:
  - implementation當下再次執行 `alembic heads`，不要在本文件硬編 revision number。
  - 建立 current single head的 child migration。
  - 新增 nullable `CareReportDraft.story`、`CareReport.story`、`MediaAsset.subject`。
  - 本integration已知的`MediaAsset.subject`語意值是：
    - `stool`：第4題後由server-side stool-photo state指派。
    - `portrait`：只有current/Emily既有generic portrait behavior確實仍被保留時才使用；不得為了預留
      可能性而新增一條非canonical generic-photo流程。
  - `subject`不得接受或信任client、postback、QR payload直接指定；只能由server-side flow/state
    指派。既有media的unknown/null值保持backward-compatible，不因本migration失效。
  - 更新 ORM models與必要 serialization；保持現有資料可讀，不作不必要 backfill。
- Non-goals: 不重命名 `CareReport*`；不建立 attendance schema；不修改 QR lifecycle schema。
- Tests: fresh upgrade、existing-data upgrade、downgrade（若專案慣例要求）、single-head assertion、model
  persistence與cross-org media access。
- Acceptance: schema與models一致，現有資料不需破壞性轉換，Alembic只有一個 head。

### P1-T02 — Replace the 13-question state machine with the frozen six-question flow

- Likely files: `services/api/app/domain/line_care_report_state.py` 及相關 unit tests。
- Required sequence:
  `Q1 → Q2 → Q3 → Q4 → conditional stool media → Q5 → Q6 → note → story → review → submit`。
- Actions:
  - 只保留六個 required keys：`walk_completion`, `activity`, `gait`, `defecation`,
    `animal_interaction`, `appearance_special_status`。
  - 使用 canonical option codes與完全凍結的繁中 wording。
  - 定義 `UNOBSERVED` sentinel與 `NO_STOOL_CODE`，不要靠 display label判斷流程。
  - Q4為 `defecation.none` 或 UNOBSERVED時直接進 Q5。
  - Q4為 normal/soft/abnormal時進 stool-photo state；upload或skip後進 Q5。
  - Back navigation需清除回退點之後不再有效的 answers/media/context；特別測 stool分支。
- Non-goals: 不恢復 care completion/feeding/water/urination等舊題；不把 stool prompt移到 Q6後；
  不保留額外 generic photo step，除非人工另行確認新需求。
- Tests: 每條 forward/back transition、六題 completeness、非法 step/key/value、Q4三種拍照分支、
  no-stool/UNOBSERVED skip、normal stool仍進照片、submit前缺題拒絕。
- Acceptance: state sequence與本文件逐步一致，所有 canonical labels有 regression assertions。

### P1-T03 — Seed/effective vocabulary and UNOBSERVED representation

- Likely files: vocabulary seed scripts、effective observation service、seed/unit tests。
- Actions:
  - 以 canonical wording更新六題 platform defaults；確認「沒走成」不可變成歷史 branch中的
    「沒走成(懶散不走)」。
  - 保留 organization extension/disabled-history的 current rules。
  - UNOBSERVED只在 domain/snapshot presentation表示，不新增 observation option row。
- Tests: exact category/option code/label sets、no legacy 13 required keys、UNOBSERVED不在 effective
  options與usage table。
- Acceptance: UI/presenter可取得正確六題 labels，CRM vocabulary沒有 UNOBSERVED option。

### P1-T04 — Implement note, story and required-note semantics

- Likely files: `line_draft_conversation.py`, `report_submission.py`, effective observation validator。
- Actions:
  - note與story獨立儲存、各自長度驗證、各自skip action。
  - 若任何 selected option requires note，note不可skip，並回傳人類可讀 option label，不顯示英文code。
  - story保持optional，不得被 required-note規則誤判。
- Tests: optional note skip、required note skip rejection、valid required note、story save/skip、empty/too-long
  handling、note/story不互相覆蓋。
- Acceptance: persistence與review摘要能分辨健康補充及小故事。

### P1-T05 — Wire answer snapshots and option usage for LINE submission

- Likely files: `line_draft_conversation.py`, `report_submission.py`, observation repositories/services。
- Actions:
  - 在 submission transaction使用 current有效／歷史 vocabulary建立 answer snapshots。
  - 將真實 option使用寫入 existing usage index，index失敗依 current rebuildable-index policy處理。
  - 為 UNOBSERVED提供固定 display snapshot，但不要將其傳給 CRM option validator或usage service。
  - 提交前繼續驗證 draft/report/animal organization binding與idempotency key。
- Tests: labels改名後舊 report仍顯示 snapshot、disabled option history、usage row建立、UNOBSERVED無usage、
  duplicate webhook不重複 report/usage。
- Acceptance: LINE submission與其他 submission consumers採相同歷史語意。

### P1-T06 — Preserve multiple reports per animal/day

- Likely files: report repository/service tests；預期不需要新增 DB constraint。
- Actions: 新增/更新 regression test，在同 organization、同 volunteer、同 animal、同 local date以不同
  draft/idempotency key提交兩筆 report。
- Acceptance: 兩筆 report都保存、都有獨立 snapshots/media/story；active draft unique rule不被誤套到 submitted history。

### Phase 1 Test and Commit Gate

1. 執行上述 targeted backend tests與新增 tests。
2. 執行 migration fresh upgrade與single-head check。
3. 執行 `uv run ruff check <changed-python-files>` 與適用的 format check。
4. 執行 `git status --short`、`git diff --stat`、完整 `git diff`、`git diff --check`。
5. 確認沒有 menu、adoption、attendance、AI或Timeline變更。
6. 全部 PASS後建立 Phase 1 dedicated commit，例如
   `feat(line): integrate volunteer walk report core`。
7. 任一 gate失敗不得進 Phase 2。

## 7. Phase 2 — Animal Selection and Draft Safety

**Dependency**：Phase 1 committed。**Scope**：application/domain/service與資料模型行為；允許最小
presenter/helper interface，但不得提前大量重寫 webhook或完成 Phase 3 delivery。

- [x] P2-T01 — Define a delivery-neutral find-dog hub model
- [x] P2-T02 — Reuse and reconcile current authorization
- [x] P2-T03 — Manual name/shelter-number search with safe pagination
- [x] P2-T04 — QR resolve as locator followed by shared confirmation
- [x] P2-T05 — Build Today List data service
- [x] P2-T06 — Shared Animal Confirmation model
- [x] P2-T07 — Active draft resume/switch transaction

### P2-T01 — Define a delivery-neutral find-dog hub model

- Likely components: new/existing application result dataclasses/types near `AnimalSelectionService`。
- Actions: 定義三個固定 actions（QR、manual search、Today List）與共用 candidate/confirmation資料模型。
- Non-goals: 不在此 task綁 Rich Menu action、不決定 webhook precedence、不發 LINE message。
- Tests: model/actions完整，presenter-neutral，不含client-supplied organization authorization。
- Acceptance: Phase 3可只負責把同一 application result轉成 LINE UI。

### P2-T02 — Reuse and reconcile current authorization

- Likely files: `animal_selection.py`, `volunteer_reporting_authorization.py`, report submission callers。
- Actions:
  - 本task是walk-report authorization reconciliation的唯一主要責任點；不要把實際DailyScope移除
    回推到Phase 1。
  - inspect current `list_candidates/resolve_qr/confirm` signatures，所有新caller傳入 server-resolved
    user/org/membership/role。
  - 在 volunteer submission前以同一 authorization service重新驗證 active membership/grant/animal。
  - 移除 walk-report path對 `ReportableScopeRepository` 的第二套 allow-list依賴；legacy DailyScope
    model/API若有其他用途，不在本 Phase順便刪除。
- Tests: revoked membership、expired grant、inactive animal、Org A user/Org B animal、membership ID mismatch。
- Acceptance: selection與submission採一致 authorization，不會「選得到但送不出」或反向繞過。

### P2-T03 — Manual name/shelter-number search with safe pagination

- Likely files: `AnimalRepository`, `AnimalSelectionService`, API/application tests。
- Actions:
  - 確認 repository query同時 partial-match name與shelter number，並固定 deterministic order。
  - 候選只含 current organization active animals。
  - 定義 page/cursor/offset與has-more資訊，禁止只取前N筆後靜默丟失。
  - 一筆結果仍回 candidate並要求 confirmation；多筆不得 auto-select。
- Tests: name partial、number partial、case/whitespace規則、0/1/many、跨頁、同名動物、cross-org exclusion。
- Acceptance: service回傳完整可分頁候選且沒有猜測。

### P2-T04 — QR resolve as locator followed by shared confirmation

- Likely files: `AnimalSelectionService`, QR repository/application tests。
- Actions:
  - reuse current tenant-scoped QR resolution與revoked/invalid token rules。
  - resolve結果只建立 confirmation model，不建立或更換 draft。
  - confirmation時再次 authorize animal/current organization。
- Tests: valid QR、invalid/revoked QR、Org B QR在Org A context得到不洩漏的not-found、resolve後draft數量不變、
  confirm後才進draft decision。
- Acceptance: QR永遠是locator，不是authorization credential。

### P2-T05 — Build Today List data service

- Likely files: animal/report repositories、organization timezone helper、application service。
- Actions:
  - 由 current authorized active-animal candidate set產生今日名單，不使用 DailyScope allow-list。
  - 以 organization timezone計算 half-open local day bounds。
  - 一次 org-scoped aggregate每隻 animal的 `report_count`與`latest_submitted_at`，避免N+1。
  - 分成未回報/已回報，兩組都保留可選狀態及pagination metadata。
  - 已回報動物再次選擇時走正常 draft decision，不disabled。
- Tests: midnight/timezone boundary、0/1/multiple reports、count/latest、兩組分頁、跨org report不計入、已回報仍可選。
- Acceptance: Today List清楚區分狀態但不把 submitted history當active draft。

### P2-T06 — Shared Animal Confirmation model

- Likely files: animal selection application types、photo projection/helper。
- Actions: 統一 QR/search/today結果為包含 name、shelter number、area、photo URL/reference、current shelter
  display與animal ID的server-built model；提供 confirm/reselect intents但不在此 Phase綁LINE postback。
- Tests: 三入口輸出同一型別、missing photo/area、current shelter正確、cross-org photo/reference不可見。
- Acceptance: Phase 3無需為三入口複製 authorization或查詢。

### P2-T07 — Active draft resume/switch transaction

- Likely files: `LineDraftService`, draft repository、application tests。
- Actions:
  - 沒有active draft：確認後create。
  - active draft animal相同：resume current state/token，不建立新draft、不回422。
  - animal不同：先回needs-confirmation result；未收到explicit confirmation前不改draft。
  - explicit switch需在同一 transaction更新animal，清除media associations、note、story與不能安全沿用的
    answers/reconfirmation context。
  - 所有draft lookup包含 organization與volunteer owner scope。
- Tests: no draft、same animal、different animal before confirm、confirmed switch、cancel switch、expired draft、
  simultaneous/replayed confirmation、media/note/story/answer cleanup、cross-user/cross-org draft。
- Acceptance: 不存在silent reassignment或上一隻animal內容洩漏。

### Phase 2 Test and Commit Gate

1. 執行 selection、authorization、today list、draft service與cross-org targeted tests。
2. 重跑 `tests/integration/test_multiple_care_reports.py` 與 QR management targeted tests。
3. 檢查 `line_webhook.py`：只允許必要 interface調整，不應已完成 menu/text/image routing。
4. 執行 Ruff、`git status --short`、`git diff --stat`、完整 `git diff`、`git diff --check`。
5. PASS後建立 Phase 2 dedicated commit，例如
   `feat(line): integrate walk report animal selection`。

## 8. Phase 3 — LINE Routing and Rich Menu Integration

**Dependency**：Phase 2 committed。**Scope**：LINE delivery、routing、presenters、Rich Menu與LIFF protocol。
所有walk-report in-chat presentation以Emily final UI為主；current architecture只提供安全routing與data。

- [x] P3-T00 — Freeze Emily's final LINE Bot UI contract before coding
- [x] P3-T01 — Wire `walk_report` and find-dog presentation
- [x] P3-T02 — Add exact command precedence and synchronize LIFF protocol
- [x] P3-T03 — Preserve adoption/walk routing isolation
- [x] P3-T04 — Dispatch LINE images by server-side state
- [x] P3-T05 — Deliver search, pagination, Today List and confirmation
- [x] P3-T06 — Preserve required-note and story text delivery
- [x] P3-T07 — Rich Menu upload hardening without IA redesign
- [x] P3-T08 — Record the handoff boundary

### P3-T00 — Freeze Emily's final LINE Bot UI contract before coding

- Likely sources: `9e534ebd`的LINE presenter/webhook output、`6374592`、`33f9023`、相關Flex preview與
  `test_line_card_readability.py`/presenter tests（實際path需先依Phase 0規則解析）。
- Actions:
  - inventory最終find-dog、question、stool photo、note、story、required-note、confirmation、summary、
    celebration、error與empty-state cards。
  - 記錄每張card的title/caption/body、glyph/sticker、tone/color、button order、alt text、postback intent與
    pagination affordance。
  - 對歷史commit有差異時，以`9e534ebd`最終狀態與本文件canonical product wording為準。
  - 將current service result fields映射到該UI contract；缺資料應使用明確empty/fallback state，不得改成
    另一套臨時plain-text流程。
- Non-goals: 不恢復舊13題、不移植Emily舊Rich Menu IA、不更動adoption UI、不為個人偏好重新設計。
- Tests/acceptance: presenter/readability snapshots或structural assertions涵蓋上述所有card種類；確認
  Flex payload符合LINE限制、alt text完整，且Emily final visual hierarchy被保留。

### P3-T01 — Wire `walk_report` and find-dog presentation

- Likely files: `line_menu_actions.py`, `line_webhook.py`, LINE presenter/Flex helpers、role menu tests。
- Actions:
  - 將 `action=walk_report` 從placeholder route移到正式 find-dog hub handler。
  - 以Emily final find-dog Flex UI顯示 QR／搜尋／今日名單三個固定入口。
  - 保留 default → 志工服務、volunteer → 返回主選單的current routing/lifecycle。
- Non-goal: `volunteer_checkin`完全不碰。
- Tests: walk action不再回「功能開發中」、三入口都可觸發、Back仍回default menu、check-in fixture/行為未變。
- Acceptance: Main → Volunteer Service → Walk Report → Find Animal可走通。

### P3-T02 — Add exact command precedence and synchronize LIFF protocol

- Likely files: `apps/web/lib/liff-line-handoff.ts`, animal confirmation page/copy、`line_webhook.py`, tests/fixtures。
- Actions:
  - 全部 protocol surface使用 exact「開始散步回報」。
  - route exact command早於 note、story、search fallback與generic chat。
  - 舊「開始照護回報」不再作 active protocol literal；backend domain names可保留。
  - active walk draft收到command時回到find/resume decision，不得把command存進文字欄位。
- Tests: LIFF send payload、manual fallback copy、exact/whitespace handling、command during note、command during story、
  near-match文字不當command。
- Acceptance: UI、LINE message、matcher與fixtures完全一致。

### P3-T03 — Preserve adoption/walk routing isolation

- Likely files: `line_webhook.py`, adoption/walk webhook tests。
- Actions:
  - 保留signature verification、event claim/idempotency、public menu、adoption start與active adoption routing。
  - 為 exact walk command建立明確route，不讓它成為adoption free text；保留adoption draft本身，除非既有產品規則
    明確取消。
  - adoption flow postback/text/image不得落入walk draft；walk actions不得落入adoption state machine。
- Tests: active adoption + ordinary adoption text、active adoption + exact walk command、active walk + adoption postback、
  duplicate/redelivery、invalid signature。
- Acceptance: 雙向flow isolation成立，未以Emily整檔覆蓋current webhook。

### P3-T04 — Dispatch LINE images by server-side state

- Likely files: webhook image branch、QR decoder helper、`LineImageService`、media tests。
- Required dispatch:
  - stool-photo state → sanitize/store/attach `subject=stool`，成功或skip後進Q5。
  - find-dog QR image context → decode QR，呼叫Phase 2 resolve，顯示shared confirmation，不建立draft。
  - 其他狀態 → 明確拒絕/提示，不附到任意draft。
- Actions: 不信任image/postback中的organization或subject；subject由server state決定。
- Tests: stool upload、stool skip、normal answer asks photo、no-stool/UNOBSERVED不進照片、QR success/failure、
  QR不可直接start、generic image rejection、cross-org decoded QR。
- Acceptance: stool與QR圖片永不互相誤分類。

### P3-T05 — Deliver search, pagination, Today List and confirmation

- Likely files: LINE presenter/Flex/quick-reply helpers、webhook postback handlers。
- Actions:
  - 將Phase 2 results轉成Emily final visual language的LINE Flex cards，不重做repository queries或authorization。
  - manual search multiple candidates顯示分頁；more action保留query/page但不信任org。
  - Today List分兩區並顯示count/latest；已回報仍有confirm action。
  - QR/search/today共用同一confirmation presenter及confirm/reselect postbacks。
  - confirm後才呼叫draft resume/switch decision；different-animal warning要求第二次explicit action。
- Tests: 0/1/many search、pagination replay、Today List兩組、同動物resume、不同動物警告/確認、confirmation欄位。
- Acceptance: delivery只呈現Phase 2已授權資料，沒有silent truncation或direct start。

### P3-T06 — Preserve required-note and story text delivery

- Likely files: LINE question/note/story/review presenters、webhook text branch。
- Actions: 使用Emily final block/sticker cards；required-note時不顯示skip；一般note可skip；story獨立提示/skip；
  review摘要分列note/story並使用snapshots labels；submit success使用Emily final celebration/feedback pattern。
- Tests: human-readable required option、text只在正確state接受、review內容、back navigation。
- Acceptance: free text不會寫入錯誤欄位或錯誤flow。

### P3-T07 — Rich Menu upload hardening without IA redesign

- Likely files: `messaging_api_adapter.py`, `sync_line_role_menus.py`及tests。
- Actions:
  - 確認upload仍使用 `https://api-data.line.me` 且保留LINE response logging。
  - 若仍hardcode PNG，讓caller依實際檔案格式傳入正確 Content-Type並驗證允許格式。
  - 保留current role-menu YAML與images；不移植Emily舊單一三格menu。
- Non-goal: 不修改/刪除/實作「志工報到」。
- Tests: PNG/JPEG content type、wrong/empty image、role definitions、existing menu navigation。
- Acceptance: IA不變，只有walk action接線與upload robustness改變。

### P3-T08 — Record the handoff boundary

- 在相關code comment或integration note保持未來hook point，但不得呼叫
  `CareReportHandoffService.consume_pending_handoff`。
- 明確標記：`Separate workstream — QR→LINE CareReportHandoff`。
- LINE chat內直接掃QR image不受此defer影響。

### Phase 3 Test and Commit Gate

1. 執行 LINE state/presenter/postback/webhook/adoption/signature/idempotency tests。
2. 執行 LIFF unit tests、`npm --prefix apps/web run test`、`npm --prefix apps/web run typecheck`。
3. 視環境執行 focused Playwright LIFF/volunteer flow；無法執行時記錄原因，不可以unit test冒充E2E。
4. 執行 Ruff、frontend format check、`git status --short`、`git diff --stat`、完整diff與
   `git diff --check`。
5. 確認Volunteer Check-in diff為零、adoption tests通過、handoff consumer仍未接線。
6. PASS後建立Phase 3 dedicated commit，例如 `feat(line): integrate walk report routing`。

## 9. Phase 4 — AI Worker and Stool Analysis

**Dependency**：Phase 3 committed且stool media可正確保存。**Scope**：async AI pipeline；不做Timeline UI。

- [x] P4-T01 — Port AIJobRunner into the current worker architecture
- [x] P4-T02 — Implement claim, stale reclaim, bounded batch and retry/backoff
- [x] P4-T03 — Add stool provider adapter and configuration
- [x] P4-T04 — Filter only stool media and preserve raw output
- [x] P4-T05 — Prove failure isolation from CareReport submission

### P4-T01 — Port AIJobRunner into the current worker architecture

- Likely files: worker handler/runner、job repository、`services/worker/worker.py`。
- Actions:
  - 以 `71cebe0`為reference建立runner，reuse current `AIProcessingJob`與worker repository。
  - 保留current volunteer-access iteration；新增獨立、bounded AI iteration，不替換entry point。
  - 每個organization先建立server-side scope，再claim/process該org jobs。
  - claim transaction與provider call分離，避免長時間持有row lock。
- Tests: current volunteer loop仍執行、AI loop執行、單一org failure不餓死其他org、cancellation與logging。
- Acceptance: worker同時服務既有volunteer jobs與AI jobs。

### P4-T02 — Implement claim, stale reclaim, bounded batch and retry/backoff

- Likely files: runner、worker job repository、integration tests。
- Actions: atomic claim token、stale timeout reclaim、per-iteration limit、max retry、exponential/capped backoff、
  terminal vs retryable errors、claim release fallback。
- Tests: competing workers只處理一次、stale claim、future `available_at`不claim、max retry、provider timeout、
  exception後claim可恢復。
- Acceptance: 不會busy-loop、永久running或跨org claim。

### P4-T03 — Add stool provider adapter and configuration

- Likely files: AI port/adapter、settings、`.env.example`, `pyproject.toml`/`uv.lock`若需要。
- Actions:
  - 以 `49327a9`為reference，加入timeout、API key header、base64 request與response validation。
  - secrets只能來自environment；log不得含API key/image bytes/PII。
  - provider未設定時依current policy使用mock或safe skip，不阻擋report。
  - 使用 `uv` 更新dependencies/lock，不手改出不一致lock。
- Tests: recognized/unrecognized、abnormality、timeout、network error、4xx terminal、5xx retry、invalid JSON、
  missing config、secret redaction。
- Acceptance: adapter輸出明確raw/formal envelope且錯誤分類可供runner使用。

### P4-T04 — Filter only stool media and preserve raw output

- Likely files: runner context loader、AI handler、AI observation repository。
- Actions:
  - 只下載current organization、attached to target report、`subject=stool`的media。
  - 無stool照片時不呼叫provider，保存safe skip/no-observation outcome。
  - 保存完整provider raw payload至AI job/observation既有JSON欄位；formal observation只產生允許的CRM描述。
  - AIObservation與job/report target全部需organization一致。
- Tests: portrait/other media排除、cross-org media排除、no image不call、raw output preservation、formal code allow-list、
  retry沿用/取代observation的current policy。
- Acceptance: stool provider看不到非stool或其他organization內容。

### P4-T05 — Prove failure isolation from CareReport submission

- Actions: 測試report transaction先成功；enqueue失敗、worker未啟動、provider失敗、observation persistence失敗時
  report仍可讀且status可重試/呈現。
- Acceptance: 沒有任何AI exception沿submission path造成CareReport rollback。

### Phase 4 Test and Commit Gate

1. 執行AI adapter unit tests、worker wiring/lifecycle integration tests、tenant-isolation tests與report failure-isolation test。
2. 重跑current volunteer worker tests，確認既有loop無regression。
3. 執行Ruff、`git status --short`、`git diff --stat`、完整diff與`git diff --check`。
4. 確認沒有Timeline frontend變更。
5. PASS後建立Phase 4 dedicated commit，例如 `feat(ai): integrate stool analysis pipeline`。

## 10. Phase 5 — Timeline Stool Analysis

**Dependency**：Phase 4 committed並能產生實際AIObservation。`9e534ebd`只作behavior reference；即使
patch可乾淨套用，也不得在此前移植。

- [x] P5-T01 — Add tenant-safe, deterministic repository lookup
- [x] P5-T02 — Define an explicit API response schema and serialization
- [x] P5-T03 — Update frontend types and mapping
- [x] P5-T04 — Render stool analysis and human review state

### P5-T01 — Add tenant-safe, deterministic repository lookup

- Likely file: `TimelineRepository`。
- Actions:
  - 查詢report IDs對應的stool AI observations。
  - 同時 filter `AIObservation.organization_id`與`AIProcessingJob.organization_id`。
  - 只接受 `target_type=care_report`、target ID在已由org-scoped timeline取得的report IDs。
  - 只解析具辨識schema的stool raw payload；其他provider output忽略。
  - 以 `created_at, id` deterministic ordering選每report最新有效observation。
- Tests: empty IDs、multiple retries、same timestamp tie、wrong target type、Org B job/observation/report排除、
  malformed raw payload。
- Acceptance: 每個report最多一個deterministic result，沒有cross-org exposure。

### P5-T02 — Define an explicit API response schema and serialization

- Likely file: animal timeline API/Pydantic response models、contract tests。
- Actions: 定義stool analysis fields：recognized、score/label、abnormality、assessment、recommendation、
  review status、human-reviewed state；不要只依 `extra="allow"`偷渡untyped dict。
- 保留staff/admin timeline authorization與server-resolved organization context。
- Tests: recognized/unrecognized、null/no-analysis、human review states、response contract、unauthorized volunteer、
  cross-org animal not found。
- Acceptance: OpenAPI/runtime serialization一致，沒有analysis時回null/omit的行為固定。

### P5-T03 — Update frontend types and mapping

- Likely files: `timelineMapping.ts`, API types/contracts consumers。
- Actions: snake_case API映射成明確camelCase UI type，保留nullable semantics，不以truthiness遺失score 0/false。
- Tests: full payload、recognized false、nullable fields、no analysis、review states。
- Acceptance: frontend typecheck通過且mapping不依未宣告extra fields。

### P5-T04 — Render stool analysis and human review state

- Likely file: `AnimalTimeline.tsx`及frontend tests。
- Actions:
  - 有analysis才顯示AI便便判讀區塊。
  - 顯示recognized/unrecognized、score label、abnormality、recommendation與human review狀態。
  - recommendation附「日常照護參考，不具醫療診斷效力」。
  - unknown/pending review state不得誤標為已確認。
- Tests: recognized、unrecognized、abnormal、pending/confirmed/rejected/corrected、empty state、不渲染空section。
- Acceptance: UI語意與API一致、可讀且不把AI輸出當醫療診斷。

### Phase 5 Test and Commit Gate

1. 執行timeline repository/API/contract tests與frontend mapping/render tests。
2. 執行 `npm --prefix apps/web run test`、`typecheck`，並視需要執行`build`。
3. 執行Ruff、frontend format check、`git status --short`、`git diff --stat`、完整diff與
   `git diff --check`。
4. 對照 `9e534ebd` 確認只取得需要的五檔行為，沒有帶回舊branch其他差異。
5. PASS後建立Phase 5 dedicated commit，例如 `feat(web): show stool analysis in animal timeline`。

## 11. Phase 6 — Integration Acceptance

**Dependency**：Phase 1–5均已有獨立commit。這是完整regression/E2E gate，不預設修改code。

- [x] P6-T01 — End-to-end volunteer walk-report acceptance
- [x] P6-T02 — Questionnaire and draft lifecycle acceptance
- [x] P6-T03 — Data, AI and Timeline acceptance
- [x] P6-T04 — Security and regression acceptance

### P6-T01 — End-to-end volunteer walk-report acceptance

- 驗證 Main → 志工服務 → 散步回報 → 找動物。
- 分別走 QR image、manual search、Today List 三條路徑。
- 每條路徑都顯示共用Animal Confirmation且在confirm前不建立/改寫draft。
- 搜尋多候選、pagination、Today List兩區/count/latest/再次回報全部驗證。

### P6-T02 — Questionnaire and draft lifecycle acceptance

- 驗證六題順序與所有exact wording。
- 驗證UNOBSERVED與normal/no-event資料語意不同。
- 驗證Q4後立即發生conditional stool-photo：normal/soft/abnormal詢問，none/UNOBSERVED跳過。
- 驗證note、story、required-note、review與submit。
- 驗證same-animal resume、different-animal warning/confirm、switch cleanup、cancel/expiry/replay。
- 驗證同animal同日多筆submitted reports與新的active draft互不阻擋。

### P6-T03 — Data, AI and Timeline acceptance

- 驗證snapshots在vocabulary label變更後保持歷史顯示。
- 驗證真實options有usage、UNOBSERVED沒有CRM usage。
- 驗證AI unavailable/provider failure仍保存report。
- 驗證AI success產生tenant-scoped raw output/AIObservation並在Timeline顯示。
- 驗證pending與human-reviewed states。

### P6-T04 — Security and regression acceptance

- 對search、QR、today list、draft、report、media、AI job、AI observation、timeline逐一執行cross-org tests。
- 重跑LINE signature、duplicate webhook、role menu與adoption isolation tests。
- 重跑QR management search/status filter/pagination/stale-request tests，確保`5b9831f`主功能未退步。
- 重跑frontend quality/typecheck/build與backend Ruff/full relevant pytest；能執行時跑focused Playwright E2E。
- 將pre-existing failure與new regression分開記錄，禁止用放寬assertion或移除security test換PASS。

### Phase 6 Stop Gate

- 全部PASS且沒有檔案修改：**不要建立empty/no-op commit**。
- 若發現regression：先記錄root cause，進行最小修正、targeted test、完整relevant regression、diff review；
  然後建立獨立 integration-fix commit，例如
  `fix(integration): resolve walk report regressions`。
- Phase 6不得把未完成的deferred work順便納入。

## 12. Deferred / Out-of-Scope Work

以下項目不屬本 integration；即使實作時發現相關hook或TODO也不得順便處理：

1. **OUT OF SCOPE — Volunteer Check-in**：保留現有placeholder，不修改、不實作、不刪除。
2. **Separate workstream — QR→LINE CareReportHandoff**：本項在 Phase 1–6 執行時明確
   deferred；後續人工授權已開啟另案實作，不回溯混入原 Phase commits。
3. Persistent QR physical replacement/label printing tracking。
4. 與本散步回報無關的 QR lifecycle hardening、QR management redesign或token policy變更。
5. Adoption redesign、adoption state/schema/menu視覺改造。
6. Backend `CareReport*` domain大規模rename；user-facing copy改為散步回報即可。
7. Emily preview assets、舊Rich Menu layout、歷史docs、demo/PowerShell helper。
8. Attendance model/API/routing、attendance作為report prerequisite。

## 13. Commit Policy

1. Phase 1–5 每個有implementation change的Phase至少一顆dedicated local commit；不得跨Phase混合。
2. 每次commit前必須：
   - `git status --short`
   - `git diff --stat`
   - 完整 `git diff`
   - `git diff --check`
   - Phase targeted tests與相關regression tests
3. Stage前逐檔確認沒有unrelated/user changes；不得使用reset/checkout丟棄不相關變更。
4. Suggested messages僅供參考，實際遵循repository convention：

```text
Phase 1  feat(line): integrate volunteer walk report core
Phase 2  feat(line): integrate walk report animal selection
Phase 3  feat(line): integrate walk report routing
Phase 4  feat(ai): integrate stool analysis pipeline
Phase 5  feat(web): show stool analysis in animal timeline
```

5. Phase 6沒有diff時不commit；若有regression fix，使用獨立integration-fix commit。
6. 禁止empty commit、禁止push、禁止force-push、禁止cherry-pick `b1f8bd8`、禁止批次cherry-pick Emily history。

## 14. Final Acceptance Checklist

- [x] Integration branch確實從exact `5b9831f`建立，baseline evidence已記錄。
- [x] Alembic保持single head；walk-report schema revision接在implementation當時的current head。
- [x] 六題順序、codes與繁中文字完全符合canonical wording，舊13題不再是required workflow。
- [x] Stool-photo在Q4後；normal/soft/abnormal詢問，none/UNOBSERVED跳過，照片可略過。
- [x] UNOBSERVED不是CRM vocabulary option，也不計入option usage。
- [x] note與story分離；required-note無錯誤skip。
- [x] LINE submissions保存answer snapshots與真實option usage。
- [x] 同animal同日可提交多筆report，Today List已回報animal仍可再次回報。
- [x] QR/search/Today List都是正式入口並共用Animal Confirmation。
- [x] Search支援name/shelter-number partial match、多候選選擇與安全pagination。
- [x] Today List分尚未/已回報，顯示count/latest local time。
- [x] QR只作locator，confirm前不建立或改寫draft。
- [x] Same animal resume；different animal warning＋explicit confirm；switch後無media/note/story/context殘留。
- [x] Selection與submission都使用current volunteer authorization，不以DailyScope作第二allow-list。
- [x] Search、QR、today、draft、report、media、AI、timeline cross-org tests通過。
- [x] 「開始散步回報」在LIFF、manual copy、webhook matcher與tests完全一致且優先於自由文字。
- [x] LINE QR/stool/generic image依server-side state正確分流。
- [x] Walk-report in-chat UI以Emily final Flex/block-sticker設計為主，find/question/media/note/story/review/success/error/empty cards均有presenter/readability coverage。
- [x] `MediaAsset.subject`只由server-side state指派；`stool`語意固定，`portrait`僅在保留既有行為時使用，unknown/null media維持相容。
- [x] Adoption與walk-report postback/text/image雙向隔離，signature/idempotency無regression。
- [x] Rich Menu保留current IA；Volunteer Check-in完全未修改。
- [x] Current volunteer worker loop保留，AI runner具claim/reclaim/bounded retry/backoff。
- [x] 只有subject=stool且同organization的media會送provider；AI failure不阻擋report。
- [x] Timeline query有雙重organization filter與deterministic latest ordering。
- [x] Timeline API schema、frontend mapping/render與human review states有完整tests。
- [x] `9e534ebd`只在Phase 5 selective port，未帶回舊branch大範圍差異。
- [x] QR management、adoption、role menu、frontend build與backend quality regression gates通過。
- [x] Phase 1–6 期間 `Separate workstream — QR→LINE CareReportHandoff`保持 deferred；
  後續僅在獲得明確人工授權後接線。
- [x] Phase 1–5各自有dedicated local commit；Phase 6無diff時沒有empty commit。
- [x] 沒有unrelated changes、沒有push，最終`git diff --check`通過。

## Unattended Execution Log

- 2026-09-02 00:52 CST — Phase 1 implementation complete. Added child migration
  `0039_walk_report_story_media` from `0038_line_adoption`; implemented the frozen six-question
  state flow, conditional stool-photo state, UNOBSERVED snapshot semantics, note/story separation,
  LINE answer snapshots and usage indexing, and same-animal/same-day multiple-report regression
  coverage. Preserved the existing DailyScope dependency for Phase 2 reconciliation. Targeted and
  contract tests: 47 passed; full suite collection: 1245 tests collected; local test DB current at
  `0039_walk_report_story_media (head)`.
- 2026-09-02 01:05 CST — Phase 2 implementation complete. Added delivery-neutral find-animal
  actions, shared confirmation projection, deterministic paginated search, timezone-aware Today
  List grouping with one tenant-scoped report aggregate, and explicit active-draft resume/switch
  decisions with full animal-context cleanup. Reconciled selection/submission authorization on
  `VolunteerReportingAuthorizationService` and removed DailyScope from walk-report creation and
  submission paths. Phase 2 targeted/security/contract tests: 50 passed.
- 2026-09-02 01:19 CST — Phase 3 implementation complete. Integrated Emily's final block/sticker
  Flex presentation with the canonical six-question copy; wired the walk menu, exact command,
  QR/search/Today List shared confirmation, safe search/Today pagination, draft resume/switch,
  required-note/story/review/success delivery, and strict adoption/walk image isolation. Added
  server-side QR image decoding and server-assigned stool media subjects; retained current Rich
  Menu IA while hardening PNG/JPEG uploads. Backend Phase 3 gate: 108 passed; frontend Vitest:
  393 passed; typecheck, Prettier, Ruff and diff checks passed. Focused Playwright reached 9/12;
  the three LINE-runtime cases used the real unavailable SDK because the current Next dev setup did
  not apply its pre-existing `LIFF_HANDOFF_E2E_MOCK` alias (the changed command contract is covered
  by passing Vitest tests); no failing product assertion was hidden or rewritten.
- 2026-09-02 01:30 CST — Phase 4 implementation complete. Preserved the volunteer-access worker
  loop and added an independent tenant-by-tenant AI loop with atomic claims, stale reclaim, bounded
  batches, capped exponential retry, terminal-error classification and cancellation propagation.
  Added the optional environment-only stool provider, raw/formal response envelope, and strict
  current-org/current-report/`subject=stool` filtering before object download. Reports without
  eligible stool media record a safe skip without a provider call. Provider, observation-persistence
  and enqueue failures leave the submitted report readable and retryable. Phase 4 adapter, worker,
  tenant-isolation, failure-isolation and existing volunteer-worker gate: 88 passed; Ruff and diff
  checks passed. No Timeline frontend files changed.
- 2026-09-02 01:38 CST — Phase 5 implementation complete. Added a deterministic
  `(created_at, id)` stool-observation lookup constrained by both job and observation organization,
  `care_report` target type and the already tenant-scoped report IDs; malformed/non-stool payloads
  are ignored and latest valid retries win. Added explicit Pydantic response models with stable
  null/no-analysis behavior, explicit frontend snake-to-camel mapping, and recognized/unrecognized,
  abnormality, assessment, recommendation/disclaimer and pending/confirmed/rejected/corrected UI.
  Focused backend gate: 17 passed; database-backed authorization gate: 6 passed; focused frontend:
  16 passed; full frontend: 400 passed. Typecheck, production build, Prettier, full Ruff and diff
  checks passed. Reviewed against `9e534ebd`; only the required timeline behavior was adapted, with
  dual-tenant filters, deterministic ties and typed contracts added rather than porting old branch
  architecture.
- 2026-09-02 01:42 CST — Phase 6 integration acceptance complete. Alembic reports the single head
  and current revision `0039_walk_report_story_media`. The full relevant backend, security,
  isolation, contract and Python E2E suite passed 244/244; the full frontend suite passed 400/400,
  with typecheck, production build, Prettier, full Ruff and diff checks passing. Focused Playwright
  passed 16/19 across QR confirmation, cross-shelter denial/switch, responsive/accessibility,
  management and timeline behavior. The remaining three LIFF runtime-mock cases reproduce the
  Phase 3 pre-existing Next 15 dev alias issue: with and without `LIFF_HANDOFF_E2E_MOCK=1`, the
  repository mock is not substituted and the real unavailable SDK leaves send count at zero. This
  is non-blocking because the unavailable fallback itself passes and the exact `開始散步回報`
  payload is covered by passing Vitest; no assertion or production code was weakened. Volunteer
  Check-in remains untouched and no production caller was added for deferred
  `consume_pending_handoff`.
- 2026-09-02 — Post-integration handoff workstream authorized. Added the trusted webhook
  consumer for exact `開始散步回報`, tenant/user-bound one-time consumption, atomic
  handoff+draft savepoint behavior, same-animal resume, and explicit server-state-only
  different-animal switch confirmation. Volunteer Check-in remains untouched.
- 2026-09-02 — Isolated the handoff LIFF mock behind a dedicated Playwright configuration,
  port 3002, non-reused server and temporary app/cache copy, with a production guard.
  The complete animal-confirmation handoff suite now passes 12/12, including supported,
  unavailable, send-failure and close-failure runtimes. Normal volunteer entry/application
  regression tests pass 52/52 without the alias.

### Diff Review Remediation

- [x] Initial selection synchronizes WebhookSession — `None → B`, `A → B`, same-shelter,
  rollback, and tenant-scoped handoff consumption regressions pass.
- [x] E2E temp cleanup is run-owned — each UUID marker names one validated temp directory;
  the concurrent ownership test proves cleanup B leaves A intact.
- [x] Revoked binding cannot create WebhookSession — the locked binding is authoritative and
  the revoke-race regression preserves the original HTTP and webhook contexts.
- [x] Verification documentation matches actual suite coverage — the 12-case handoff spec and
  separate 8-case manager QR/A4 spec are listed independently.
- [x] Temp app copy excludes local .env secrets — `.env*` is excluded except the explicit safe
  `.env.example`, with filter regression coverage.
