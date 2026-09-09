# Adoption Inquiry 與 Growth Diary 功能合併暨調整計畫書

## 1. 基本資訊（Metadata）

| 項目 | 內容 |
| --- | --- |
| 來源分支／Commit | `origin/feature/growth-diary-daily-thread-and-adoption-fixes`／`d8542374bb9d5fa2d338ffe24895167d185aab4c` |
| 來源提交者 | 資淺工程師 |
| 目標分支／Commit | `main`／`f5ccc36c9d86b2aa0ed4ac8024d594c289f0cdff` |
| 共同祖先 | `0bcd9fe5769b6049f06264ea7bb67401ae3b940e` |
| 計畫產生日期 | 2026-09-07（Asia/Taipei） |
| 文件狀態 | Draft／待執行、待指定審查人核准 |
| 合併判定 | `Needs rework`：不得直接合併 `d854237` 至 `main` |
| 預定整合方式 | 從目標 `main` 建立 pre-merge 整合分支，選擇性移植 `d854237`，完成重構及驗證後以 Pull Request squash merge |
| 發布原則 | Schema-first、additive migration、feature flag 漸進啟用、可回退 application、不執行 production schema downgrade |

### 1.1 計畫目標

安全整合以下功能，同時保留 `main` 現有的多收容所隔離、Google Auth、LINE 對話版本控制、Growth Diary 管理 API、AI provenance、媒體安全政策及不可變 GCE 發布流程：

- Adoption inquiry 管理收件匣。
- 領養問卷自由文字擷取與 AI 適配度欄位保存。
- Growth Diary 同日訊息合併（daily thread）。
- Growth Diary 管理端狀態與搜尋／日期篩選。
- Growth Diary LINE 回顧圖片的短效公開 capability URL。
- Growth Diary 多模態 AI 分析及飼養問題回覆。
- Adoption hub LINE rich menu 設定與圖片。

### 1.2 已知整合限制

- `main` 相對共同祖先已有約 69 個後續提交，來源分支僅有 1 個新提交；來源分支是以過時架構完成。
- `main` 的 Alembic head 為 `0051_join_applications`，來源分支另建立 `0042` 至 `0044` migration 鏈，直接加入會形成 multiple heads。
- Growth Diary、LINE webhook、Gemini client、前端頁面與測試均有雙方同時修改，不能用整檔選擇 `ours` 或 `theirs` 解決。
- 除非確認 `d854237` 的 migration 已在任何共享環境執行，否則預設將其 schema 變更重編為接在 `0051_join_applications` 後的新 migration。

### 1.3 停止條件

遇到以下任一情況時，停止合併並回到架構審查：

- `origin/main` 已不再指向 `f5ccc36c9`，且新增提交涉及本功能相關檔案。
- 發現 `0042_adoption_freetext_profile`、`0043_growth_diary_status` 或 `0044_growth_diary_daily_thread` 已套用至共享測試／正式資料庫。
- Migration dry run 無法由 `0051_join_applications` 無資料損失升級。
- 整合後 Alembic 仍有多個 head。
- 任一跨 shelter 隔離、LINE signature、authentication 或 authorization 測試失敗。
- 新版本 schema 無法讓上一個正式 application release 安全啟動。

## 2. 合併前置修改要求（Pre-merge Refactoring Tasks）

以下項目必須在 pre-merge 整合分支完成，並由至少一位熟悉 backend／database 的審查者核准後，才可建立正式合併 PR。

### PM-01：以 `main` 架構為基準重整變更

**修改原因**

來源提交的 Growth Diary API、model、repository 與前端頁面建立在舊版架構上。若直接採用來源版本，會覆蓋 `main` 已加入的 typed API、AI provenance、媒體驗證、Google Auth 與 LINE stale-action 防護。

**預期修改方向**

- 保留 `main` 的模組與 API 邊界，以小範圍 patch 移植功能。
- 不以 `git checkout --theirs <file>` 整檔取代衝突檔案。
- 保留 `AdoptionDraft.interaction_version`、`lock_by_token()`、`lock_active_for_adopter()`、expected state/version 驗證及 webhook event claim。
- 保留 `GrowthDiaryManagementService`、detail endpoint、authenticated photo endpoint、AI provenance 欄位及既有 frontend feature components。

### PM-02：重建單一路徑 Alembic migration

**修改原因**

來源分支的 migration 從 `0041_growth_diary` 分叉，與 `main` 的 `0042_growth_diary_management` 至 `0051_join_applications` 形成兩條 head；來源 migration 還會立即刪除 `photo_key`，使 application rollback 失去相容性。

**預期修改方向**

- 未曾套用至共享環境時，移除或捨棄來源分支的 `0042` 至 `0044` migration，建立唯一的新 revision，例如 `0052_adoption_growth_diary_features`，其 `down_revision` 必須是 `0051_join_applications`。
- 新 migration 應新增：
  - `adoption_drafts.freetext_profile_rounds`
  - `adoption_inquiries.ai_recommendation_overridden`
  - `growth_diary_entries.status`
  - `growth_diary_entries.photo_keys`
  - `growth_diary_entries.entry_date`（若採資料庫唯一性方案）
  - `growth_diary_drafts.current_entry_id`
  - `growth_diary_drafts.entry_date`
  - status 更新稽核欄位（若需求確認採用）
- 從既有 `photo_key` 回填 `photo_keys`，但第一階段保留 `photo_key`、`photo_content_type` 與全部 AI provenance 欄位。
- 部署過渡期採雙讀／雙寫或相容讀取，不在本次 migration 直接 drop 舊欄位。
- 若來源 migration 已在共享環境套用，保留既有 revision identity，改採 Alembic merge revision；未完成資料庫盤點前不得改寫 migration。

### PM-03：修正 Growth Diary daily-thread 併發問題

**修改原因**

來源實作在判斷 `current_entry_id`／`entry_date` 前未鎖定 `GrowthDiaryDraft`，append 前也未鎖定 `GrowthDiaryEntry`。兩個不同 LINE event 同時抵達時，可能建立兩篇同日日記，或讓 note／photo list 發生 lost update。

**預期修改方向**

- 在同一個 database transaction 內以 `SELECT ... FOR UPDATE` 鎖定該 adopter 的 diary draft。
- append 時以 `entry_id + organization_id + adopter_user_id + inquiry_id + animal_id` 查詢並鎖定 entry。
- 將 `entry_date` 寫入 `GrowthDiaryEntry`，並評估加入以下唯一約束：

```python
UniqueConstraint(
    "organization_id",
    "inquiry_id",
    "adopter_user_id",
    "entry_date",
    name="uq_growth_diary_daily_entry",
)
```

- 對唯一鍵衝突採 retry／重新讀取既有 entry，不直接回傳 500。
- 新增兩個獨立 transaction 並行送入同一 adopter 的整合測試。

### PM-04：恢復 repository 層資料完整性與 tenant 防護

**修改原因**

來源版 `GrowthDiaryRepository.add_entry()` 移除了 `main` 對 inquiry、animal、adopter、organization 與媒體格式的驗證；`append_to_entry()` 只依 entry UUID 讀取。這不符合 shelter-owned data 必須明確 server-side scope 的核心要求。

**預期修改方向**

- `add_entry()` 和 `append_to_entry()` 均明確驗證 `organization_id`。
- 驗證 inquiry 的 `target_animal_id`、`adopter_user_id` 及 `organization_id` 與輸入一致。
- 驗證 animal 屬於同一 organization。
- 保留 RLS，同時在 repository query 加入 tenant predicate，採雙層防護。
- 不以 `ValueError` 表示 domain failure；改用不洩漏資源存在性的 404 `DomainError`。
- 保留「文字或照片至少一項」及可信 MIME type 檢查。

### PM-05：維持 Growth Diary API 向後相容

**修改原因**

來源提交將既有 response 從 `ai_analysis`／`photo_endpoint` 改為 `ai_mood`／`photo_urls`，並改變 query parameters。這會破壞 `main` 的 frontend、contract tests 與外部 consumer。

**預期修改方向**

- 保留既有 endpoint、response model、detail endpoint 與 `query`／`mood` 行為。
- 以 additive 欄位加入 `status`、日期篩選與 `photo_endpoints`。
- 若欄位語意無法相容，新增 versioned endpoint，不原地變更既有 contract。
- 更新 OpenAPI、generated TypeScript contract 與所有 frontend consumer。
- 日期篩選需明確採 organization timezone，而不是默認 UTC 日界線。

### PM-06：整合 Growth Diary 多圖媒體安全模型

**修改原因**

來源管理 API 直接回傳 MinIO signed URL，與 `main` 的 authenticated proxy endpoint、trusted content type、`no-store` 與媒體一致性驗證衝突。來源 public LINE route 也未查驗 formal media metadata。

**預期修改方向**

- 管理端繼續透過受驗證的 API photo endpoint 讀取，不直接將 MinIO endpoint 暴露給瀏覽器。
- 多圖改為 `/v1/management/growth-diary-entries/{entry_id}/photos/{photo_index}` 或使用不可猜測的 media ID。
- LINE public capability token 必須綁定：purpose、organization、entry、object key digest、expiry。
- Public route 需驗證照片確實屬於該 entry、已完成 sanitization、EXIF 已移除且 MIME 為允許的 image type。
- 所有 token 驗證失敗統一回傳 404，避免 resource enumeration。
- public base URL 僅接受已設定或可信 proxy 產生的 HTTPS origin。

### PM-07：修正 Gemini client lifecycle 與 AI 結果競態

**修改原因**

來源版 `GeminiClient` 移除了 `aclose()`，但 `main` worker 仍依賴此介面；同一篇 daily entry 每次追加訊息都啟動背景分析，也可能讓較舊結果覆蓋較新內容並重複發送 concern 通知。

**預期修改方向**

- 保留 `GeminiClient.aclose()`，所有自行建立 client 的路徑以 `try/finally` 關閉。
- 保留 `main` 的 AI provenance 與 raw output 欄位。
- 為 diary content 增加 `content_version` 或等價 fingerprint；背景 job 寫回前確認版本仍一致。
- 優先使用既有 worker/job infrastructure，對同一 entry 的工作去重或 debounce。
- concern 通知加入 idempotency key，例如 `entry_id + content_version + concern`。
- 限制 AI input/output 長度，解析後以 Pydantic schema 驗證 mood、文字長度及欄位型別。

### PM-08：限制單日內容與資源用量

**修改原因**

來源實作持續串接 note 與 `photo_keys`，未限制單日訊息數、文字長度、照片數與 AI prompt 大小，可能造成 DB 寫入錯誤、回應過大及 AI 成本失控。

**預期修改方向**

- 定義並集中管理：單則文字、單日累積文字、單日照片數、單張圖片及 AI prompt 的上限。
- 超限時回覆明確的使用者訊息，不產生部分寫入。
- LINE history 與 management list 僅回傳摘要；完整內容由 detail endpoint 取得。
- 圖片 URL 採 lazy loading，不在列表對每張圖片預先產生 signed URL。
- 對 `%keyword%` 搜尋評估 PostgreSQL trigram／適當 index，至少保留慢查詢監控。

### PM-09：補齊狀態轉換與稽核

**修改原因**

Adoption inquiry status 有 actor 欄位，但 Growth Diary status 沒有更新者、時間與 audit；任意來回切換狀態也沒有 transition policy。

**預期修改方向**

- 使用 `Literal`／enum 定義 API 輸入與 domain status。
- 在 service 層驗證允許的狀態轉移。
- 保存 `status_updated_at`、`status_updated_by_user_id`。
- 透過既有 `AuditService` 記錄 before／after、actor、organization、resource ID。
- 確認 STAFF、SHELTER_ADMIN、PLATFORM_ADMIN 的可見與可修改邊界。

### PM-10：抽離重複問卷定義

**修改原因**

來源提交在 webhook、AI service 與 inbox service 維護三份 question label／option 對照表，註解要求人工同步，違反 DRY 並容易造成畫面、AI prompt 與保存資料語意不同。

**預期修改方向**

- 將純 domain metadata 抽到不依賴 API／infrastructure 的模組。
- webhook、AI prompt 與 inbox presenter 共用同一份 question definitions。
- 保留 layer direction：application/domain 不得 import API router。
- 加入 contract test，驗證所有 required key 都有 label 與可接受選項。

### PM-11：前端沿用既有 feature architecture

**修改原因**

來源提交將 Growth Diary 完整頁面直接寫入 route file，但 `main` 已採 `features/growth-diary` component、API client、types 與 CSS module 架構。

**預期修改方向**

- route file 保持薄層，只 render `GrowthDiaryPage`。
- 將 status、日期篩選與多圖 UI 加入既有 feature components、API client 與 TypeScript types。
- Adoption inquiry inbox 若沒有對應 feature folder，依現有 management feature 慣例拆分，不在單一 page 放置全部 query、state、types 與 styling。
- 避免全域 CSS；優先使用現有 UI components 與 scoped CSS module。
- 驗證 loading、empty、401、403、404、409、422 與 network error 狀態。

### PM-12：Rich menu 保持 dry-run，待功能上線後發布

**修改原因**

Rich menu 是外部、立即影響使用者的設定；若在 schema 或 webhook 尚未完成前發布，使用者會進入無法完成的流程。

**預期修改方向**

- 合併時可納入 YAML 與圖片，但不可在整合階段使用 `--apply` 發布。
- dry-run 驗證 menu schema、role mapping、圖片尺寸與 MIME。
- 待 production health、LINE webhook 與 feature flag 驗證完成後另行批准發布。
- 保存現行 rich menu ID／mapping，確保可以復原。

## 3. 合併執行步驟（Step-by-step Merge Guide）

### 3.1 準備與基準確認

所有命令均由 repository root 執行。開始前不得有未提交變更：

```bash
git status --short --branch
git fetch origin --prune
git rev-parse origin/main
git rev-parse d854237
git merge-base f5ccc36c9 d854237
```

預期：

```text
origin/main = f5ccc36c9d86b2aa0ed4ac8024d594c289f0cdff
d854237    = d8542374bb9d5fa2d338ffe24895167d185aab4c
merge-base = 0bcd9fe5769b6049f06264ea7bb67401ae3b940e
```

若 `origin/main` 已前進，先重新執行 impact analysis，不應自行將本計畫套用到未知 commit。

### 3.2 建立可追溯備份 ref

```bash
git branch backup/main-before-adoption-20260907 f5ccc36c9
git branch backup/adoption-source-d854237 d854237
```

確認：

```bash
git show --no-patch --oneline backup/main-before-adoption-20260907
git show --no-patch --oneline backup/adoption-source-d854237
```

這些 branch 只作為本地／團隊可見的 Git ref，不代替正式 release receipt 或 database backup。

### 3.3 從目標 main 建立 pre-merge 整合分支

```bash
git switch main
git pull --ff-only origin main
git switch -c integration/adoption-growth-diary-d854237
```

再次確認：

```bash
git status --short --branch
git rev-parse HEAD
```

HEAD 必須是已審查的目標 commit；若不是 `f5ccc36c9`，停止並更新計畫基準。

### 3.4 將來源提交套用但暫不提交

```bash
git cherry-pick --no-commit d854237
```

發生衝突是預期結果。不要執行整體 `ours`／`theirs` 策略。使用：

```bash
git status --short
git diff --name-only --diff-filter=U
git diff --cc
```

逐檔解決後：

```bash
git add <已確認的檔案>
git diff --cached --check
git status --short
```

若需要放棄此次套用並回到乾淨整合分支：

```bash
git cherry-pick --abort
```

不得在共享的 `main` 使用 `git reset --hard`、force push 或直接修改歷史。

### 3.5 預期衝突檔案與處理原則

| 檔案／區域 | 衝突類型 | 處理原則 |
| --- | --- | --- |
| `services/api/app/api/line_webhook.py` | 雙方大量修改 | 以 `main` 為骨架；保留 signature verification、event claim、current-flow routing、interaction version，再逐函式移植 adoption／daily-thread 功能。禁止採整檔 `theirs`。 |
| `services/api/app/application/line_adoption_conversation.py` | 對話狀態與 idempotency | 保留 `main` 的 row lock、expected state/version、stale action 防護；將 free-text profile 與 recommendation override 合併到既有 state machine。 |
| `services/api/app/persistence/repositories/adoption_draft_repository.py` | repository API 名稱與鎖定策略 | 保留 `get_*` read methods及 `lock_*` mutation methods，不將一般讀取全部改成鎖定讀取。 |
| `services/api/app/domain/line_adoption_state.py` | state graph | 合併新 free-text states，但保留 `main` 的 replay／version semantics；逐條檢查 transition 與 back mapping。 |
| `services/api/app/api/growth_diary.py` | API contract | 保留 typed response、detail 與 authenticated photo endpoints；以 additive 方式增加 status、date filter、多圖欄位。 |
| `services/api/app/application/growth_diary_service.py` | 服務整體替換 | 保留 `GrowthDiaryManagementService` 與 AI provenance；加入 status workflow 和多圖 presenter。 |
| `services/api/app/persistence/models/growth_diary.py` | 欄位互斥 | 合併欄位而非二選一；保留 `photo_key` 過渡欄位、`photo_content_type`、全部 AI provenance，再新增 daily-thread／status 欄位。 |
| `services/api/app/persistence/repositories/growth_diary_repository.py` | 安全 invariant 被來源版本移除 | 保留 `main` 的 tenant/source/media checks 與 management query；另加鎖定式 daily append。 |
| `services/api/app/application/growth_diary_ai_analysis_service.py` | multimodal 與 provenance | 同時保留 multimodal input、prompt／output schema version、raw output 與分析狀態。 |
| `services/api/app/infrastructure/ai/gemini_client.py` | client contract | 保留 `aclose()` 與 worker 相容性，再加入 image parts 與 extraction API。 |
| `services/api/app/application/media_access.py` | public token 與既有安全 helper | 新增 diary capability helper，不改壞 adoption token；token 不攜帶未受保護的可替換 tenant identity。 |
| `services/api/app/api/media.py` | public／management 媒體路徑 | 保留既有 media authorization；新增 public diary route 時套用 explicit organization、entry ownership、MIME、sanitization 驗證。 |
| `services/api/app/main.py` | router registration | 保留全部 `main` router，僅新增 adoption inquiry router；重新生成 OpenAPI 並檢查 public route security。 |
| `services/api/app/config/settings.py` | settings 雙方新增 | 保留現有 production safety settings；新增設定要有明確 default、environment example 與 runtime validation。 |
| `services/api/migrations/versions/*` | 分叉 migration | 不直接提交來源 `0042` 至 `0044`；依 PM-02 建立接在 `0051` 後的新 revision，或經審查採 merge revision。 |
| `apps/web/app/(management)/growth-diary/page.tsx` | add/add conflict | 保留 `main` 的薄 route，功能移入 `apps/web/features/growth-diary/`。 |
| `apps/web/app/(management)/growth-diary/page.test.tsx` | add/add conflict | 合併 route smoke test 與 query contract test，不刪除任一現有安全／render assertion。 |
| `apps/web/app/(management)/management-query.ts` | 新 query builder | 保留現有 builders，新增函式；不得更改其他管理頁 query contract。 |
| `apps/web/components/management/AppSidebar.tsx` | 導航與權限變更 | 以 `main` 的角色／sidebar 結構為準，只新增經授權的 adoption inbox entry。 |
| `apps/web/app/globals.css` | 全域樣式衝突 | 不移植可由現有 component／CSS module 實現的全域規則。 |
| `pyproject.toml`／`uv.lock` | Python version、dependency lock | 保留 `main` 的 Python 3.12／tool settings，只新增 Windows 條件式 `tzdata`；以 `uv lock` 重新生成 lockfile。 |
| `tests/**` | 測試雙方修改 | 以 `main` 現有 regression tests 為基礎，移植來源測試並補併發、migration、tenant、API contract 測試。不得以來源測試取代主幹測試。 |

### 3.6 完成 pre-merge 修正與分段提交

建議依風險分段提交，方便審查與 bisect：

```bash
git commit -m "refactor(adoption): port inquiry workflow onto current conversation controls"
git commit -m "feat(adoption): add tenant-scoped inquiry management inbox"
git commit -m "feat(growth-diary): add concurrency-safe daily threads"
git commit -m "feat(growth-diary): extend management API without breaking contracts"
git commit -m "feat(media): add validated LINE diary photo capability"
git commit -m "test(adoption): cover migration concurrency and tenant isolation"
```

提交名稱可依實際 staged scope 調整；每個 commit 必須通過 `git diff --cached --check`，不得混入無關檔案。

### 3.7 與最新 main 同步

在正式 PR 審查前：

```bash
git fetch origin --prune
git rebase origin/main
```

此處只允許 rebase 尚未共享或已明確協調的 integration branch。解衝突後重新執行完整驗證。

### 3.8 建立 PR 與合併

- PR base：`main`
- PR head：`integration/adoption-growth-diary-d854237`
- 至少需要 backend/database 與 frontend 各一位審查者。
- PR 必須附：migration graph、schema compatibility 判定、測試結果、手動 smoke evidence、feature flag 預設值與 rollback target。
- 所有 required checks 通過後採 squash merge。
- Squash commit message 建議：

```text
feat(adoption): integrate inquiry inbox and safe growth-diary daily threads
```

## 4. 測試與驗證計畫（Testing & Verification Checklist）

### 4.1 自動化測試

#### A. 靜態品質與 migration graph

```bash
git diff --check origin/main...HEAD
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check services tests scripts
UV_CACHE_DIR=/tmp/uv-cache uv run alembic heads
UV_CACHE_DIR=/tmp/uv-cache uv run alembic history
```

驗收條件：

- 無 whitespace error。
- Ruff 通過。
- Alembic 僅有一個 head，且是本次新 revision。

#### B. Backend targeted tests

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/unit/test_line_adoption_state_machine.py \
  tests/unit/test_gemini_client.py \
  tests/unit/test_growth_diary_ai_analysis_service.py \
  tests/integration/test_adoption_conversation_flow.py \
  tests/integration/test_adoption_webhook_flow.py \
  tests/integration/test_adoption_inquiry_inbox_service.py \
  tests/integration/test_growth_diary_webhook_flow.py \
  tests/integration/test_growth_diary_repository.py \
  tests/integration/test_growth_diary_inbox_service.py \
  tests/integration/test_growth_diary_management.py \
  tests/integration/test_growth_diary_management_migration.py \
  tests/integration/test_growth_diary_media_consistency.py \
  tests/integration/test_growth_diary_reminder_handler.py \
  tests/security/test_growth_diary_management_isolation.py \
  tests/contract/test_growth_diary_management_contract.py
```

若整合時調整了檔名，應更新清單，但不可略過對應測試範圍。

#### C. Backend full regression

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
```

#### D. Frontend tests

```bash
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
npm --prefix apps/web run format:check
npm --prefix apps/web run test:e2e:critical
npm --prefix apps/web run test:e2e -- e2e/growth-diary-management.spec.ts
```

新增 adoption inquiry E2E 後，將其加入最後一條命令。

#### E. Repository 整體驗證

```bash
./scripts/verify_local.sh
```

### 4.2 必須新增或擴充的自動化情境

#### Adoption conversation

- 同一 postback event 重送只處理一次。
- 不同 event 但攜帶舊 `interaction_version` 時回傳 stale action，不覆蓋新答案。
- free-text extraction 與按鈕回答同時發生時，不遺失答案。
- AI suitability 結果在 draft 已取消、過期或進入其他狀態時不得寫回。
- 提交 inquiry 時正確保存 AI score／explanation 與 recommendation override。
- 來源 animal 不屬於 draft organization 時回傳 404／409，不洩漏另一 shelter 資料。

#### Adoption inquiry inbox

- STAFF／SHELTER_ADMIN 只能讀取 active organization 的 inquiry。
- organization A 的 inquiry ID 在 organization B context 下讀取或更新皆回傳 404。
- 無 membership、VOLUNTEER 或 inactive membership 不可讀取 PII。
- status 非法值回傳 422。
- status 更新保存 actor、timestamp 與 audit record。
- 搜尋、日期、status、path 與 pagination 組合條件正確。

#### Growth Diary daily thread

- 同一 organization timezone、同一 inquiry、同一天的文字與照片合併為單一 entry。
- 跨日第一則訊息建立新 entry。
- 同一天切換動物再切回時符合已確認的業務規則。
- 兩個 database transaction 同時追加時不產生 duplicate daily entry，且 note／photos 均不遺失。
- 同一 webhook event redelivery 不重複新增照片或文字。
- 超過單日文字／照片上限時不產生部分寫入。
- stale／mismatched `current_entry_id` 不得寫入其他 adopter、animal、inquiry 或 organization。

#### AI analysis

- 無 credential 時標記 `unconfigured`，主流程仍成功。
- Gemini timeout、500、malformed JSON 時標記 failed 且不回滾日記。
- 舊 content version 的結果不得覆蓋新版內容。
- multimodal request 僅送出 sanitised image 與可信 MIME。
- `GeminiClient` 在成功、失敗及取消路徑均關閉 HTTP client。
- concern 通知具 idempotency，同一 version 不重複推送。

#### Media

- public token 過期、被修改、用途錯誤、entry 不符、organization 不符時皆回傳 404。
- token 雖有效但 object key 不在 entry 內時回傳 404。
- 非 image、未 sanitise 或 metadata 不可信的 object 不得回傳。
- management photo endpoint 驗證 authentication、role 與 active shelter scope。
- 回應含 `X-Content-Type-Options: nosniff` 與核准的 cache policy。

#### Migration

- 空資料庫可升級到新 head。
- 從 `0051_join_applications` 可升級到新 head。
- 舊 `photo_key = NULL`、有效 photo key、legacy AI rows 都能正確回填。
- 升級後 `photo_key`、`photo_content_type`、AI provenance 不遺失。
- 上一版 application 可在升級後 schema 啟動並完成 health check。

### 4.3 手動冒煙測試

#### Smoke-01：既有登入與 shelter context

1. 使用 Google 帳號登入。
2. 選擇 shelter A，確認管理首頁可開啟。
3. 切換 shelter B，確認頁面資料重新載入。
4. 嘗試以 shelter A 的 inquiry／diary URL 在 shelter B context 存取。
5. 預期：回傳 404 或權限拒絕，不顯示 shelter A 的姓名、電話、日記或照片。

#### Smoke-02：心有所屬領養流程

1. 從 LINE 啟動領養媒合。
2. 選擇 shelter 與指定動物。
3. 使用自由文字填入部分條件，再以逐題流程補齊缺漏。
4. 快速重複點擊前一題與目前題目的按鈕。
5. 完成 AI suitability、姓名、聯絡時間、電話與送出。
6. 預期：沒有答案倒退／覆蓋，只有一筆 inquiry，AI score／explanation 正確保存。

#### Smoke-03：推薦名單領養流程

1. 選擇推薦名單流程並完成問卷。
2. 驗證 AI 不可用時仍能看到 rule-based fallback。
3. 從 AI 建議中選擇動物，再測試「瀏覽其他動物」。
4. 完成提交。
5. 預期：target animal 正確、override flag 符合選擇情境、沒有跨 shelter 候選。

#### Smoke-04：Adoption inquiry 管理收件匣

1. 以 STAFF 登入 shelter A。
2. 開啟領養意願頁面。
3. 依姓名、電話、動物、path、status、日期篩選。
4. 查看完整問卷。
5. 將狀態改為 contacted，再改回允許狀態。
6. 預期：列表、分頁、PII 權限、更新時間與 audit record 正確。

#### Smoke-05：Growth Diary 同日合併

1. 完成一筆領養 inquiry。
2. 從 LINE 啟動毛孩日記並選擇動物。
3. 依序傳送：文字、照片、第二段文字、第二張照片。
4. 不重新點擊「新增一篇」。
5. 預期：只有一篇當日 entry，文字順序與照片順序正確，沒有訊息遺失。

#### Smoke-06：Growth Diary 跨日與切換動物

1. 以測試 clock 或測試資料模擬 organization timezone 跨日。
2. 在隔日傳送新訊息。
3. 切換另一隻已領養動物，再切回原動物。
4. 預期：依核准的 daily uniqueness 規則建立或重用 entry，不混入其他動物內容。

#### Smoke-07：AI 與 staff concern 通知

1. 傳送一般近況，確認 adopter 收到一般 AI 回覆。
2. 傳送疑似疾病／受傷描述，確認回覆包含適當的聯繫收容所／就醫提示。
3. 確認 shelter STAFF 收到一次 concern 通知。
4. 在 AI 分析進行中追加內容。
5. 預期：最終資料對應最新版內容，舊分析不覆蓋，通知不重複。

#### Smoke-08：LINE 回顧圖片

1. 從 LINE 開啟日記回顧。
2. 確認 carousel 可由 LINE server 載入圖片。
3. 修改 token、entry ID 或等待 token 過期後重新請求。
4. 預期：正常 token 顯示圖片；異常與過期 token 一律為 404。

#### Smoke-09：既有管理功能回歸

1. 驗證 animals、reports、AI review、volunteer access、account／invitation 與 Google login。
2. 驗證 Growth Diary 原有 detail、AI provenance 與 authenticated photo view。
3. 預期：沒有 API shape、路由、sidebar、CSS 或 authentication regression。

#### Smoke-10：Rich menu dry-run

1. 執行 dry-run，不帶 `--apply`：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m scripts.sync_line_role_menus \
  --image-dir infra/local/rich-menu-images
```

2. 確認角色 mapping、圖片與 action URL 正確。
3. 未取得發布核准前不得執行 `--apply`。

## 5. 異常回退計畫（Rollback Plan）

### 5.1 合併前／合併過程回退

Cherry-pick 尚未完成時：

```bash
git cherry-pick --abort
```

Rebase 尚未完成時：

```bash
git rebase --abort
```

完成整合但尚未合併 main 時，直接關閉 PR 或捨棄 integration branch；不得修改 `main`。

### 5.2 已合併 main、尚未部署

若採 squash merge：

```bash
git switch main
git pull --ff-only origin main
git revert <SQUASH_MERGE_COMMIT>
git push origin main
```

若實際採 merge commit：

```bash
git switch main
git pull --ff-only origin main
git revert -m 1 <MERGE_COMMIT>
git push origin main
```

Revert 必須經 PR／required checks，不可 force push、reset shared main 或刪除遠端歷史。

### 5.3 測試環境部署失敗

1. 立即關閉 adoption inbox、daily thread、public diary photo 與 rich menu feature flag。
2. 保存 release SHA、migration revision、redacted logs 與失敗 request／event ID。
3. 若 migration 尚未執行，重新部署上一個已知正常 release。
4. 若 additive migration 已執行，保留 schema，不執行 downgrade；部署上一版 application 並執行 smoke test。
5. 若上一版 application 無法在新 schema 啟動，停止回退並建立修正 release roll-forward。

### 5.4 Production application rollback

Production 使用 repository 既有不可變 release 流程。先從成功 deployment receipt 取得核准的 `N-1` release ID，並確認本次 release manifest 的 schema compatibility 為 `backward-compatible-with-previous`。

```bash
sudo /opt/strayhub/current/infra/gce/scripts/rollback-release.sh \
  --target-release "$N_MINUS_ONE_RELEASE_ID" \
  --deployment-role "StrayHub production deployment operator" \
  --confirm-rollback ROLLBACK_STRAYHUB_APPLICATION
```

Rollback 原則：

- 只切換 application artifact，不執行 database downgrade。
- 不使用 mutable image tag。
- 不執行 `docker compose down -v`，不得刪除 PostgreSQL／MinIO volume。
- 若 schema compatibility 為 `unknown` 或 `forward-only`，rollback script 應拒絕；此時建立新的 immutable fix release 進行 roll-forward。
- 回退後驗證 release receipt、實際 image digest、API／Web health、worker、PostgreSQL 與 MinIO。

### 5.5 Production roll-forward

修正完成後建立新的 immutable release。若需重新啟用 receipt 記錄的較新版本，且 migration revision 完全相同，可使用：

```bash
sudo /opt/strayhub/current/infra/gce/scripts/rollforward-release.sh \
  --target-release "$RECORDED_NEWER_RELEASE_ID" \
  --deployment-role "StrayHub production deployment operator" \
  --confirm-rollforward ROLLFORWARD_STRAYHUB_APPLICATION
```

不得用 roll-forward 跳過尚未執行的 migration，亦不得選擇任意未經 receipt 驗證的 release。

### 5.6 資料與外部狀態復原

- Schema：本次必須設計為 additive；production 不執行 destructive downgrade。
- Daily entries：若發生 duplicate／lost update，先停用寫入 flag，保留原始 event IDs，再以審查過的修復 script 處理；不得直接手動刪除 production rows。
- Object storage：不得因 application rollback 刪除新照片；保留 object，待資料修復後重新關聯或依 retention policy 清理。
- AI results：可將錯誤結果標記 invalid／failed 後重新排程，不覆蓋原始 provenance／raw output。
- LINE rich menu：保存發布前 mapping；若新 menu 已發布，使用官方同步工具回復舊 mapping，不以未追蹤的手動 UI 操作處理。
- PII 或跨 shelter 暴露：立即關閉受影響 endpoint／feature flag，視為安全事件，保存 audit evidence 並依 incident process 通報，不僅執行一般功能 rollback。

## 6. 工作待辦清單（Implementation Checklist）

- [ ] 指定整合負責人、backend/database reviewer、frontend reviewer 與 release approver。
- [ ] 確認 `origin/main` 仍為 `f5ccc36c9d86b2aa0ed4ac8024d594c289f0cdff`；若已前進，重新執行 impact analysis。
- [ ] 確認來源 commit 為 `d8542374bb9d5fa2d338ffe24895167d185aab4c`。
- [ ] 確認工作樹乾淨且沒有需要保留的未提交修改。
- [ ] 盤點來源 `0042` 至 `0044` migration 是否已套用至任何共享環境。
- [ ] 建立 `backup/main-before-adoption-20260907` ref。
- [ ] 建立 `backup/adoption-source-d854237` ref。
- [ ] 從核准的 `main` 建立 `integration/adoption-growth-diary-d854237` 分支。
- [ ] 以 `git cherry-pick --no-commit d854237` 套用來源提交。
- [ ] 列出並保存所有 unmerged paths 供 PR 說明使用。
- [ ] 以 `main` 為基準解決 `line_webhook.py` 衝突。
- [ ] 保留 LINE `X-Line-Signature` 驗證與 event claim／redelivery idempotency。
- [ ] 保留 AdoptionDraft interaction version、row lock 與 stale action 防護。
- [ ] 將 free-text profile state 整合到目前 state machine。
- [ ] 將 AI recommendation override 整合到目前 inquiry submission flow。
- [ ] 抽離共用 adoption question definitions，移除三份人工同步映射。
- [ ] 建立接在 `0051_join_applications` 後的單一路徑 migration，或依共享環境狀態建立 merge revision。
- [ ] 保留 `photo_key`、`photo_content_type` 與全部 AI provenance 欄位。
- [ ] 新增 `photo_keys`、daily entry date、status 與 draft thread pointer 欄位。
- [ ] 完成既有 `photo_key` 到 `photo_keys` 的無損 backfill。
- [ ] 實作上一版 application 對新 schema 的相容性策略。
- [ ] 在同一 transaction 鎖定 GrowthDiaryDraft 後再判斷同日 entry。
- [ ] 在 append 時鎖定並驗證 GrowthDiaryEntry 的 organization、adopter、inquiry 與 animal。
- [ ] 決定並實作 daily entry 唯一約束與 retry 行為。
- [ ] 恢復 GrowthDiary repository 的 source、content、MIME 與 tenant invariant checks。
- [ ] 保留 GrowthDiary typed management API、detail endpoint 與 AI provenance contract。
- [ ] 以 additive 方式加入 status、日期篩選與多圖 API。
- [ ] 更新 OpenAPI 與 generated TypeScript contracts。
- [ ] 管理端多圖維持 authenticated proxy，不直接暴露 MinIO signed URL。
- [ ] 完成 LINE public photo token 的 purpose、tenant、entry、object、expiry 與 MIME 驗證。
- [ ] 驗證 public base URL 僅能使用可信 HTTPS origin。
- [ ] 保留 `GeminiClient.aclose()` 並修正所有 client lifecycle。
- [ ] 保留 AI provenance、raw output、prompt version 與 output schema version。
- [ ] 增加 AI content version／fingerprint，防止舊結果覆蓋新內容。
- [ ] 對同一 diary entry 的 AI job 實作去重或 debounce。
- [ ] 對 concern staff 通知加入 idempotency key。
- [ ] 定義並實作單則文字、單日文字、照片數、圖片大小與 AI prompt 上限。
- [ ] Growth Diary status 更新加入 actor、timestamp、transition validation 與 audit。
- [ ] Adoption inquiry status 更新補齊 audit 與角色權限測試。
- [ ] 將 Growth Diary 前端功能移植到既有 `apps/web/features/growth-diary` 架構。
- [ ] 將 Adoption inquiry 前端拆分為符合現有 feature／API client／types 慣例的結構。
- [ ] 僅在核准角色的 sidebar 顯示 Adoption inquiry inbox。
- [ ] 合併雙方 Growth Diary 與 adoption tests，不刪除 `main` regression coverage。
- [ ] 新增 daily thread 雙 transaction 併發測試。
- [ ] 新增 AI stale-result 與 duplicate concern notification 測試。
- [ ] 新增跨 shelter inquiry、entry、status、photo isolation tests。
- [ ] 新增 public token tampering、expiry、wrong-purpose 與 wrong-tenant tests。
- [ ] 新增 migration empty DB、0051 upgrade、legacy data backfill 與 N-1 compatibility tests。
- [ ] 執行 `git diff --check origin/main...HEAD`。
- [ ] 執行 Ruff targeted／full checks。
- [ ] 執行 Alembic heads／history，確認只有一個 head。
- [ ] 在空資料庫執行 `alembic upgrade head`。
- [ ] 在 `0051_join_applications` 且含 legacy diary data 的資料庫執行 migration dry run。
- [ ] 執行 backend targeted unit、integration、security 與 contract tests。
- [ ] 執行 backend full pytest regression。
- [ ] 執行 frontend test、typecheck、build 與 format check。
- [ ] 執行 Growth Diary 與 Adoption inquiry E2E tests。
- [ ] 執行 `./scripts/verify_local.sh`。
- [ ] 完成 Google login 與 shelter context 手動 smoke test。
- [ ] 完成心有所屬與推薦名單 LINE smoke test。
- [ ] 完成 Adoption inquiry inbox 搜尋、PII、status 與 audit smoke test。
- [ ] 完成 Growth Diary 同日、跨日、切換動物與併發 smoke test。
- [ ] 完成 AI fallback、concern、stale result 與通知去重 smoke test。
- [ ] 完成 LINE history public photo URL 與 token failure smoke test。
- [ ] 完成既有 animals、reports、AI review、volunteer、account／invitation 回歸測試。
- [ ] 對 rich menu 執行 dry-run，確認未使用 `--apply`。
- [ ] 更新 PR 說明中的 migration graph、schema compatibility、測試結果與 rollback target。
- [ ] 取得 backend/database reviewer 核准。
- [ ] 取得 frontend reviewer 核准。
- [ ] 確認 required CI checks 全數通過。
- [ ] 與最新 `origin/main` rebase，並重新執行必要驗證。
- [ ] 以 squash merge 合併至 `main`。
- [ ] 確認合併後 `main` 的 Alembic head、OpenAPI、frontend build 與 full CI。
- [ ] 建立 schema-first 測試環境 release，feature flags 預設關閉。
- [ ] 完成測試環境 smoke test 與 isolation 驗證。
- [ ] 以測試 shelter 漸進啟用 Adoption inquiry 與 daily thread。
- [ ] 確認監控沒有 5xx、migration、LINE push、AI job、media fetch 或 tenant-scope 異常。
- [ ] 將 production release manifest 的 schema compatibility 設為經審查的正確值。
- [ ] 確認 production `N-1` immutable release 與 receipt 可用。
- [ ] 部署 production additive schema 與 application release。
- [ ] 完成 production health、receipt、image digest 與核心 smoke verification。
- [ ] 取得另行發布核准後才執行 rich menu `--apply`。
- [ ] 觀察漸進發布期間的錯誤率、AI 成本、daily entry duplicate、concern 通知與媒體載入率。
- [ ] 穩定觀察期完成後再評估移除 legacy `photo_key`／相容欄位，另開獨立 migration 與 PR。
