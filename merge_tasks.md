# LINE Bot 安全整合任務清單

**目標**：以 `origin/main@0b60692c2fa0988ef3645b4de41dda05eecab85f` 為不可退讓的安全基線，整合 `origin/feat/line-role-rich-menu@179de5380c2fb442b5c1ba80d504f4ec9607da63`，並將 `origin/dev/adopting_line_bot@29a2b9e6e640cdacf5d873ac90501157bbec1091` 中「正式領養 LINE 對話」所需的 dependency-closed 最小切片接到公開 Rich Menu 的「領養流程」。

**執行限制**：本文件只定義工作，不授權建立 branch、merge、commit、push、PR 或部署。每個 Stop Gate 未通過前不得進入下一階段；不得以 `ours`／`theirs` 大範圍覆蓋，不得移除 DB、production、authentication、authorization 或 tenant-isolation guard 來換取測試通過。

**已確認產品邊界**：公開入口固定只有「志工服務」與「領養流程」。志工、已領養者與工作人員 Rich Menu 都是後端驗證身分後才切換的個人選單；工作人員功能不得出現在公開入口。

**已確認行為決策**：領養流程包含「心有所屬」與「推薦我」，其中 deterministic matching 為必要能力、adoption-specific AI 僅為 optional enhancement；送出領養申請不等於完成領養，只有收容所正式確認完成領養後才可切 adopter menu，若目前沒有正式 completion lifecycle 則本次不自動切換；多收容所工作人員必須先由後端驗證 memberships，再明確選定目前收容所，才可進入該收容所的 staff menu context，`PLATFORM_ADMIN` 不得跳過選擇；production 合併後預設不啟用 LINE 新功能，必須等 secrets、Rich Menu／LIFF IDs、preflight 與真實 LINE smoke 全部通過後再啟用。

## Gate 0：已確認採用方案 2

`29a2b9e` 是測試收尾 commit；實作主要來自同一分支較早的 `8395c06`，並混有成長日記、Gemini、領養後台與 7 個 migration。已確認採用混合式最小整合：

- 完整 merge `origin/feat/line-role-rich-menu@179de538`，以 merge commit 保留 Rich Menu／志工／工作人員 LINE 開發線歷史。
- 不 merge 或單獨 cherry-pick `origin/dev/adopting_line_bot@29a2b9e`；改以新的 semantic integration commits 移植正式領養 LINE 對話及必要 dependency closure，並在 commit／PR 記錄來源 SHA。
- 預設排除 Growth Diary、Growth Diary worker、非必要領養後台、branch 自帶 CI 改寫，以及和領養 LINE 流程無關的 Gemini 內容。
- 「推薦我」路徑以 deterministic matching 為必要基線；若納入 adoption-specific AI，只可加入最小 adapter/service 並保留 deterministic fallback，AI 未設定、timeout 或失敗不得阻止建立 draft、取得推薦、選擇動物或送出領養申請。

在 T006 的 dependency-closure manifest 經審核以前，不得開始移植 adoption 開發線內容；manifest 只能確認方案 2 的逐檔邊界，不能擴張成完整 branch merge。

## Phase 1：建立可重現的整合基線

**目的**：先鎖定 heads、merge base、工作目錄與回滾點，避免分析期間來源分支移動。

- [x] T001 將 `origin/main`、`origin/feat/line-role-rich-menu`、`origin/dev/adopting_line_bot` 的完整 SHA、取得時間及 `git status --short --branch` 記錄到 `merge_tasks.md`
- [x] T002 驗證 role branch merge base 必須為 `16a7fb99e690032efe9216106c3dc89575fd12f6`，並將 `git rev-list --left-right --count origin/main...origin/feat/line-role-rich-menu` 結果記錄到 `merge_tasks.md`
- [x] T003 驗證 `origin/main` 仍是 `0b60692c2fa0988ef3645b4de41dda05eecab85f`、role source 仍是 `179de5380c2fb442b5c1ba80d504f4ec9607da63`、adoption source 仍是 `29a2b9e6e640cdacf5d873ac90501157bbec1091`；任一不符即在 `merge_tasks.md` 標記 `STOP_SOURCE_MOVED`
- [x] T004 執行 `git diff --check origin/main` 並以 `uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .` 建立 pre-merge baseline，結果記錄到 `merge_tasks.md`
- [x] T005 [P] 產生 main、role branch、adoption branch 三方 changed-file inventory，依 Textual／Semantic／Runtime config／Data safety／Deployment／Coverage gap 分類到 `merge_tasks.md`
- [x] T006 建立 `29a2b9e` dependency-closure manifest，逐檔標記 REQUIRED／OPTIONAL／EXCLUDED、來源 commit 與理由，至少涵蓋 `services/api/app/api/line_webhook.py`、`services/api/app/application/line_adoption_*.py`、`services/api/app/domain/line_adoption_state.py`、`services/api/app/persistence/models/adoption_*.py`、`services/api/app/persistence/repositories/adoption_*.py`、`services/api/migrations/versions/0038_adoption_matching.py` 至 `0044_growth_diary_ai_and_reminders.py`、`services/worker/worker.py`、`apps/web/`、`tests/integration/test_adoption_webhook_flow.py`，並確認每個 REQUIRED／OPTIONAL 項目符合方案 2
- [x] T007 在取得執行授權後，從已驗證的 main SHA 建立 `integration/line-after-db-isolation`，並將起點與可刪除的臨時 integration branch 名稱記錄到 `merge_tasks.md`
- [x] T008 建立「main 永不回退、integration branch 可整支捨棄、禁止 force-push main」的回滾檢查點並記錄到 `merge_tasks.md`

**Stop Gate 1**：T001–T008 完成，heads 與 merge base 完全符合預期；否則停止並重新分析。

### Phase 1 執行紀錄（2026-09-01，Asia/Taipei）

#### T001–T003：來源鎖定

- 取得時間：`2026-09-01T00:15:23+0800`；先執行 `git fetch origin main feat/line-role-rich-menu dev/adopting_line_bot`，以下不是 fetch 前的 stale remote-tracking refs。
- `origin/main`：`0b60692c2fa0988ef3645b4de41dda05eecab85f`
- `origin/feat/line-role-rich-menu`：`179de5380c2fb442b5c1ba80d504f4ec9607da63`
- `origin/dev/adopting_line_bot`：`29a2b9e6e640cdacf5d873ac90501157bbec1091`
- role merge base：`16a7fb99e690032efe9216106c3dc89575fd12f6`（符合固定值）。
- `git rev-list --left-right --count origin/main...origin/feat/line-role-rich-menu`：`43 7`（main-only 43、role-only 7）。
- adoption merge base（inventory 用）：`7ef854c23b123b37c023959224b47389cdfb79b9`；`origin/main...origin/dev/adopting_line_bot` 為 `39 7`。
- fetch 後三個 head 均符合固定 SHA；狀態為 `SOURCE_LOCKED`，未觸發 `STOP_SOURCE_MOVED`。
- 建 branch 前：`## fix/separate-demo-test-db...origin/fix/separate-demo-test-db`、`A  merge_tasks.md`。建 branch 後：`## integration/line-after-db-isolation`、`A  merge_tasks.md`。除此檔外，工作樹相對 `origin/main` 無差異。

#### T004：pre-merge baseline

- `git diff --check origin/main`：PASS。
- `uv run ruff check .`：PASS（`All checks passed!`）。
- `uv run ruff format --check .`：PASS（675 files already formatted）。
- 首次 `uv run pytest`：`43 failed, 1054 passed, 2 skipped, 28 errors`；根因是專用 `strayhub_test` 的 Alembic metadata 同時殘留祖先 `0032_public_volunteer_directory` 與後代 `0034_volunteer_service_dates`，使 0035–0037 未套用並造成 `animals.sex` 不存在及後續 transaction-aborted 連鎖錯誤。
- 僅對 `strayhub_test` 以 `alembic stamp --purge 0034_volunteer_service_dates` 校正冗餘 metadata，再 `alembic upgrade head` 到 main 的單一 head `0037_animal_external_sources`；未碰 `strayhub` demo DB。
- 校正後完整 `uv run pytest`：`2 failed, 1095 passed, 2 skipped`（74.28s）。兩個既有 failure 均在 `tests/unit/test_volunteer_self_status_api.py`，是 `caplog` 收不到預期 INFO 訊息；單檔重跑仍為 `2 failed, 1 passed`，與 DB、LINE integration 或本次文件變更無關。
- baseline 判定：`KNOWN_BASELINE_FAILURE`；Phase 1 已建立可重現基線，但後續 full-suite 比較不可把這兩個既有 logging assertion failure 誤判為本次 merge regression，也不得靜默忽略或放寬 assertion。

#### T005：三方 changed-file inventory

狀態來源分別為：

```text
git diff --name-status 16a7fb99e690032efe9216106c3dc89575fd12f6..origin/main
git diff --name-status 16a7fb99e690032efe9216106c3dc89575fd12f6..origin/feat/line-role-rich-menu
git diff --name-status 7ef854c23b123b37c023959224b47389cdfb79b9..origin/dev/adopting_line_bot
```

下表的 path scope 都是「與上述對應 diff 的交集」，六類互斥且合計等於完整 `--name-status` inventory；A／M／D／R 狀態以命令輸出為準。adoption 的 95 個檔案另在 T006 逐檔列出。

| Source | Textual | Semantic | Runtime config | Data safety | Deployment | Coverage gap | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| main | 19 | 7 | 5 | 8 | 110 | 28 | 177 |
| role | 5 | 13 | 34 | 0 | 0 | 9 | 61 |
| adoption | 6 | 40 | 15 | 18 | 1 | 15 | 95 |

- **Textual**：`README.md`、`CLAUDE.md`、`review.md`、`volunteer_entry.md`、`docs/**`、`specs/**`；但 `docs/deployment/**`、`docs/verification/**` 歸 Deployment。
- **Semantic**：`apps/web/**` 的應用程式頁面／元件、`services/api/app/api/**`、`services/api/app/application/**`、`services/api/app/domain/**`、LINE/AI infrastructure、worker handler/entry point，以及未落入其他類別的 scripts。Role 的 13 檔集中在 auth、webhook、menu routing、staff animal input、volunteer lifecycle、LINE adapter、API registration 與 worker handler；adoption 的 40 檔集中在 LINE adoption、matching/inquiry、growth diary 與 management UI/API。
- **Runtime config**：`.env.example`、`.dockerignore`、`.gitignore`、`.gitattributes`、`pyproject.toml`、`uv.lock`、`package.json`、`settings.py`、`infra/local/**`、`line-liff/**` 與 LINE demo/menu sync/render scripts。
- **Data safety**：`services/api/migrations/**`、persistence models/repositories、test/demo seed DB guards、`scripts/test_database.py`、migration env 與 worker DB session。Adoption 此類共 18 檔，包含 7 個 migrations（0038–0044）。
- **Deployment**：`.github/workflows/**`、`docs/deployment/**`、`docs/verification/**`、`infra/edge-nginx/**`、`infra/gce/**`、`infra/gcp-platform/**`、被移除／搬遷的 `infra/gcp-demo/**` 與 release/acceptance scripts。Main 的 110 檔是不可回退的 GCE／production baseline；adoption 的唯一 Deployment 檔是舊 `infra/gcp-demo/line-rich-menu.yaml`。
- **Coverage gap**：`tests/**`。此分類同時表示已新增／修改的 coverage evidence；每個 Semantic／Runtime／Data safety／Deployment 變更若沒有對應測試，仍須在後續 phase 當作 coverage gap 補齊。
- 重疊熱點：`.env.example`、`README.md`、`services/api/app/config/settings.py`、`services/api/app/api/line_webhook.py`、`services/api/app/main.py`、LINE adapter、management animals、OpenAPI、volunteer menu tests 與 demo/menu scripts，必須 semantic merge，不可整檔採 `ours`／`theirs`。

#### T006：`29a2b9e` dependency-closure manifest

Manifest 涵蓋 adoption diff 的全部 95 個檔案：38 REQUIRED、12 OPTIONAL、45 EXCLUDED。`來源 commit` 是該 source branch 對該檔的最後實質 touch；REQUIRED 代表只移植支援正式 LINE adoption 與其可運作資料設定的 semantic slice，不代表整檔照搬。

**REQUIRED — source `8395c0618c44cac28bc1b576eef78f9b9788e978`**

- `apps/web/app/(management)/animals/[animalId]/page.tsx`
- `apps/web/app/(management)/management-query.ts`
- `apps/web/app/(management)/shelters/page.tsx`
- `apps/web/features/adoption/AdoptionProfileFormDialog.tsx`
- `packages/contracts/src/openapi.ts`
- `services/api/app/api/management_animals.py`
- `services/api/app/api/organization_management.py`
- `services/api/app/application/adoption_matching_service.py`
- `services/api/app/application/line_adoption_draft_service.py`
- `services/api/app/application/management_animal_service.py`
- `services/api/app/persistence/models/__init__.py`
- `services/api/app/persistence/models/animal.py`
- `services/api/app/persistence/models/identity.py`
- `services/api/app/persistence/repositories/adoption_draft_repository.py`
- `services/api/app/persistence/repositories/adoption_inquiry_repository.py`
- `services/api/app/persistence/repositories/animal_repository.py`
- `services/api/app/persistence/repositories/organization_repository.py`
- `services/api/migrations/versions/0038_adoption_matching.py`
- `services/api/migrations/versions/0039_adoption_region_match.py`
- `specs/001-volunteer-care-report/contracts/openapi.yaml`
- `tests/integration/test_management_animal_adoption_profile.py`
- `tests/integration/test_management_animals.py`
- `tests/integration/test_management_workbench_api_boundaries.py`
- `tests/unit/test_line_adoption_draft_service.py`

理由：這一組提供 deterministic matching、draft/inquiry persistence、動物 `is_adoptable`／媒合欄位、收容所 region，以及在既有管理介面安全設定這些必要資料的最小閉包。Management slice 只保留動物領養 profile 與 organization region；不含 adoption inquiry inbox 或 Growth Diary 後台。OpenAPI 與 TypeScript consumer 必須隨 API contract 同步。

**REQUIRED — source `29a2b9e6e640cdacf5d873ac90501157bbec1091`**

- `services/api/app/api/line_webhook.py`
- `services/api/app/application/adoption_inquiry_submission.py`
- `services/api/app/application/line_adoption_conversation.py`
- `services/api/app/application/line_adoption_flex.py`
- `services/api/app/domain/adoption_matching.py`
- `services/api/app/domain/line_adoption_state.py`
- `services/api/app/persistence/models/adoption_draft.py`
- `services/api/app/persistence/models/adoption_inquiry.py`
- `services/api/migrations/versions/0043_adoption_inquiry_adopter_name.py`
- `tests/integration/test_adoption_conversation_flow.py`
- `tests/integration/test_adoption_webhook_flow.py`
- `tests/unit/test_adoption_matching.py`
- `tests/unit/test_line_adoption_flex.py`
- `tests/unit/test_line_adoption_state_machine.py`

理由：這一組完成正式 LINE conversation、狀態機、Flex output、詢問單提交與核心 tests。`line_webhook.py` 只採 adoption channel routing slice；Growth Diary、Gemini orchestration、舊 rich-menu switching 與任何繞過既有 webhook signature/idempotency 的段落都不得帶入。

**OPTIONAL — source `29a2b9e6e640cdacf5d873ac90501157bbec1091`**

- `.env.example`
- `pyproject.toml`
- `uv.lock`
- `services/api/app/application/adoption_ai_analysis_service.py`
- `services/api/app/config/settings.py`
- `services/api/app/infrastructure/ai/__init__.py`
- `services/api/app/infrastructure/ai/gemini_client.py`
- `services/api/migrations/versions/0041_adoption_ai_suitability.py`
- `services/api/migrations/versions/0042_adoption_ai_followup_marker.py`
- `tests/unit/test_gemini_client.py`

理由：只供 adoption-specific AI enhancement；預設不納入最小切片。若後續納入，只取 adoption AI 設定／adapter／nullable schema，必須有 timeout、invalid-output、no-credential fallback，且 deterministic recommendation 和 inquiry submission 不得依賴 AI。

**OPTIONAL — source `3de28adc8c024260d5b09c0a5f488dc7b91931a6`**

- `.gitattributes`

理由：LF enforcement 可降低 shell portability 風險，但不是 adoption runtime dependency；若採用須和 main/role 的既有 executable bit、LF 契約一起審查。

**OPTIONAL — source `8395c0618c44cac28bc1b576eef78f9b9788e978`**

- `scripts/adoption_chat_demo.py`

理由：只可作 local-only smoke helper，不得成為 production route、寫 demo DB 測試身分或攜帶 credential。

**EXCLUDED — source `8395c0618c44cac28bc1b576eef78f9b9788e978`**

- `CLAUDE.md`
- `apps/web/app/(management)/adoption-inquiries/page.tsx`
- `apps/web/components/management/icon-map.ts`
- `apps/web/components/management/ui-status.ts`
- `docs/agents/domain.md`
- `docs/agents/issue-tracker.md`
- `docs/agents/triage-labels.md`
- `infra/gcp-demo/line-rich-menu.yaml`
- `infra/local/line-rich-menu-default.jpg`
- `infra/local/line-rich-menu-path_select.png`
- `infra/local/line-rich-menu-region_select.jpg`
- `infra/local/line-rich-menu-volunteer.png`
- `infra/local/line-rich-menu.png`
- `infra/local/line-rich-menu.yaml`
- `scripts/generate_rich_menu_image.py`
- `scripts/sync_line_rich_menu.py`
- `services/api/app/api/adoption_inbox.py`
- `services/api/app/api/growth_diary.py`
- `services/api/app/application/ports/line_messaging.py`
- `services/api/app/infrastructure/line/messaging_api_adapter.py`
- `services/api/app/infrastructure/line/mock_adapter.py`
- `services/api/migrations/versions/0040_growth_diary.py`
- `tests/unit/test_line_volunteer_application_menu.py`
- `tests/unit/test_sync_line_rich_menu.py`

理由：agent docs、舊 GCP demo/menu toolchain、非必要 adoption inquiry inbox、Growth Diary，以及已由 role branch 提供的 LINE adapter/menu lifecycle 均不屬 adoption 最小切片。

**EXCLUDED — source `29a2b9e6e640cdacf5d873ac90501157bbec1091`**

- `apps/web/app/(management)/adoption-inquiries/[inquiryId]/page.tsx`
- `apps/web/app/(management)/growth-diary/page.tsx`
- `apps/web/app/globals.css`
- `apps/web/components/management/AppSidebar.tsx`
- `services/api/app/application/adoption_inbox_service.py`
- `services/api/app/application/growth_diary_ai_analysis_service.py`
- `services/api/app/application/growth_diary_service.py`
- `services/api/app/application/line_growth_diary_flex.py`
- `services/api/app/domain/growth_diary_reminder.py`
- `services/api/app/main.py`
- `services/api/app/persistence/models/growth_diary.py`
- `services/api/app/persistence/repositories/growth_diary_repository.py`
- `services/api/migrations/versions/0044_growth_diary_ai_and_reminders.py`
- `services/worker/app/handlers/growth_diary_reminder_handler.py`
- `services/worker/worker.py`
- `tests/integration/test_growth_diary_reminder_handler.py`
- `tests/integration/test_growth_diary_webhook_flow.py`
- `tests/unit/test_growth_diary_reminder.py`

理由：Growth Diary、其 AI/reminder/worker、非必要 adoption inbox UI、global CSS/sidebar，以及 source branch 的 router/warmup 混合改動全部排除。`services/worker/worker.py` 明確為 EXCLUDED，Phase 6 只能保留 role branch 核准的 volunteer handler，不註冊 Growth Diary job。

**EXCLUDED — source `beabf729cf65462758ef26cee6e3c10dd14f0159`**

- `scripts/demo-line.sh`
- `scripts/demo.sh`

理由：adoption branch 的 cold-start/stale-process 版本不是 adoption dependency；`demo-line.sh` 由 role merge 的版本在 T013 單獨 semantic review，`demo.sh` 不移植。

**EXCLUDED — source `37ff34b575c659eb50f7c578ee49f856e420b33c`**

- `README.md`

理由：避免帶入 adoption branch 的混合開發說明；最終文件依 main production/local DB 契約在 Phase 9 重寫。

Manifest security constraints：

1. Source 0038 對 `organization_id IS NULL` draft 的 RLS 允許過寬，且 source `get_active_for_adopter` 是跨 organization query；不得原樣移植。整合版必須以 server-resolved LINE binding/internal user 限定 draft owner，並新增跨 LINE user、跨 shelter、duplicate webhook tests。
2. Source organization repository 的跨收容所 listing 只能成為最小 public adoption projection；不得在整個 webhook session 設 platform scope，也不得暴露 animal、membership 或未啟用 shelter 資料。
3. Migrations 0038–0044 不照號碼／依賴鏈 cherry-pick。整合版從 main 當時的實際 head 建立新 migration，只合併 0038、0039、0043 的必要內容；0040、0044 永遠排除。若採 OPTIONAL AI，0041／0042 的 nullable 欄位另以不依賴 0040 的新 revision 加入。
4. `adoption_inquiries`、animals 與 organization queries 必須保留 `organization_id` filter/RLS；公開 adopter 只能操作自己的 draft/inquiry，client-supplied organization/animal id 不可建立授權。
5. apps/web REQUIRED 只為既有 shelter/animal 管理頁提供 region 與 adoption profile 的必要設定面；adoption inquiry inbox、Growth Diary、sidebar 導航與相關樣式均排除，符合方案 2。
6. 所有 OPTIONAL 均可整組不採用；任何 OPTIONAL 被採用時仍須保留 deterministic baseline、main runtime safety 與 role branch 的 menu/auth lifecycle，不得擴張成完整 adoption branch merge。

#### T007–T008：integration branch 與 rollback checkpoint

- 使用者「完成 Phase 1」視為 T007 的 branch-create 執行授權。
- 建立時間：`2026-09-01T00:37:12+0800`。
- 臨時 branch：`integration/line-after-db-isolation`。
- 起點／目前 HEAD：`0b60692c2fa0988ef3645b4de41dda05eecab85f`，精確等於驗證後 `origin/main`。
- 已移除 Git 自動建立的 `origin/main` upstream，避免裸 `git push` 誤推 main；目前 branch 無 upstream。
- rollback checkpoint：`origin/main` 永不 reset/rebase/force-push；integration 失敗時可整支刪除並從上述 SHA 重建；已 merge 後只允許新 revert/fix PR，不改寫 main 歷史。
- 本階段未 merge、commit、push、開 PR 或部署。

**Stop Gate 1：PASS（source integrity / reproducible baseline）**。T001–T008 完成，三個 heads 與 role merge base 精確符合預期，integration HEAD 鎖在 main base。另有 `KNOWN_BASELINE_FAILURE`（兩個既有 logging assertions）需在後續 regression ledger 持續追蹤，但不是來源移動或 tenant-isolation gate failure。

## Phase 2：先整合角色 Rich Menu 開發線

**目的**：保留 role branch 歷史，以 semantic merge 讓 LINE 功能適配 main 的 DB／production baseline。

- [x] T009 將 `origin/feat/line-role-rich-menu@179de538` 以 `--no-commit --no-ff` merge 到 integration branch，先保存 conflict 清單到 `merge_tasks.md`，未審完不得建立 merge commit
- [x] T010 逐段 semantic merge `.env.example`，同時保留 demo DB=`strayhub`、test DB=`strayhub_test` 說明與 `LINE_RICH_MENU_*_ID`、`WEB_PUBLIC_BASE_URL`、LIFF／Messaging API 空白範例，禁止真實 credential
- [x] T011 [P] semantic merge `README.md`，保留 main 的 local/production 操作契約並加入 LINE 文件索引，不得把 test fixture 指令描述為 demo seed
- [x] T012 semantic merge `services/api/app/config/settings.py`，保留 main 的 runtime safety、database、migration、KMS、secret、worker validation，再加入 LINE／LIFF／Rich Menu 設定；以 production fail-closed 為優先
- [x] T013 審查 `scripts/demo-line.sh` 的 timeout 變更，只保留 cold-start 容錯，確認它不呼叫 `scripts.seed_local`／測試 fixture、不寫入 demo DB 測試身分，並在 `tests/contract/test_local_product_quality_contract.py` 補契約測試
- [x] T014 [P] 檢查所有已合併 shell script 與 `.gitattributes` 的 LF／可執行權限，使用 `bash -n scripts/demo-line.sh line-liff/serve-demo.sh` 驗證
- [x] T015 對所有 conflict 檔案在 `merge_tasks.md` 記錄 conflict type、預期最終行為、採用段落與驗證方式，確認不存在 conflict marker 後才建立 role-source merge commit

**Stop Gate 2**：role branch 可編譯且 conflict resolution ledger 完整；不得只以 Git merge 成功視為通過。

### Phase 2 執行紀錄（2026-09-01，Asia/Taipei）

- `git merge --no-commit --no-ff origin/feat/line-role-rich-menu` 自動完成，沒有 Git textual conflict；仍逐檔完成 semantic review，未使用整檔 `ours`／`theirs`。
- `.env.example`：保留 main 的 demo/test DB 契約及假 credential，只新增空白 `LINE_RICH_MENU_{DEFAULT,VOLUNTEER,ADOPTER,STAFF}_ID`。
- `services/api/app/config/settings.py`：main 的 non-local runtime safety、database/migration、KMS/secret/worker validators 均保留；LINE IDs 全空時 role routing no-op，production enable/fail-closed 契約留在 Phase 7 完成。
- `README.md`：保留 main local/production 說明，只新增 LINE 文件索引；未加入 test fixture 作為 demo seed 的敘述。
- `scripts/demo-line.sh`：只採用 tunnel/API/Web cold-start timeout 增加；新增 `tests/contract/test_local_product_quality_contract.py` 契約，禁止 `scripts.seed_local`、`scripts.test_local`、pytest、`strayhub_test`、ORG-A 與重設 `DATABASE_URL`。
- Shell validation：`bash -n scripts/demo-line.sh line-liff/serve-demo.sh` PASS；兩檔都是 UTF-8 executable、無 CRLF。
- Python format：將 role source 新增／修改的 11 個 Python 檔依 main Ruff formatter 正規化；`ruff check` PASS、相關檔 `ruff format --check` PASS。
- Focused regression：74 passed，涵蓋 LINE adapter lifecycle、role menu actions、staff input、volunteer menu、LIFF exchange、expiration、DB-backed staff animal input及 local product contract。第一次 sandbox 執行的 4 個 DB test 是 localhost socket `PermissionError`，允許連線至專用 local test DB 後 4/4 PASS，並非程式 failure。
- Conflict ledger：Textual conflict 無；semantic hot spots 為 `.env.example`、`README.md`、`settings.py`、`demo-line.sh`，最終行為如上。`line_webhook.py`、staff authorization、adopter placeholder 與 role context 已成功引入，但依計畫必須在 Phase 3–5 繼續收斂，不能視為最終 production behavior。

**Stop Gate 2：PASS**。Role source 已 semantic merge、格式化並通過 74 個 focused tests；merge commit 建立後才進入 adoption slice。

## Phase 3：公開入口與領養流程（US1，P0）

**Goal**：任何 LINE 使用者看到的公開 Rich Menu 只有兩個入口，領養入口直接啟動正式 adoption conversation，而不是 placeholder LIFF。

**Independent Test**：未綁定 LINE 使用者點「志工服務」只進志工申請；點「領養流程」送出 `action=start_adoption_matching&flow=adoption` 並建立／續接自己的 adoption draft；「心有所屬」與「推薦我」在 AI 不可用時都能完成；公開選單不存在 staff action。

- [ ] T016 [P] [US1] 先在 `tests/unit/test_line_role_menu_actions.py` 與 `tests/unit/test_sync_role_menus_env_writeback.py` 新增公開 menu 僅允許 `start_volunteer_application`、`start_adoption_matching` 的失敗測試
- [ ] T017 [P] [US1] 先在 `tests/integration/test_adoption_webhook_flow.py` 新增 Rich Menu 入口建立／續接 draft、重送 webhook 不重複建立 draft、跨 LINE user 不可讀取 draft 的失敗測試
- [ ] T018 [US1] 將 `infra/local/line-rich-menu-default.yaml` 的公開入口固定為「志工服務」→ `action=start_volunteer_application` 與「領養流程」→ `action=start_adoption_matching&flow=adoption`，移除 shelter_info、staff、placeholder adoption action
- [ ] T019 [US1] 同步 `scripts/rich_menu_images/render.mjs` 與 `infra/local/rich-menu-images/default.png` 的兩格文案、座標及 action 對應，確認 YAML imagemap bounds 不重疊且涵蓋完整畫布
- [ ] T020 [US1] 依 T006 核准 manifest 移植 `services/api/app/domain/line_adoption_state.py`、`services/api/app/application/line_adoption_draft_service.py`、`services/api/app/application/line_adoption_conversation.py` 與 `services/api/app/application/line_adoption_flex.py`，讓 webhook 只負責通道路由，業務狀態與驗證留在 service/domain
- [ ] T021 [US1] 依 T006 核准 manifest 移植必要的 `services/api/app/persistence/models/adoption_draft.py`、`services/api/app/persistence/models/adoption_inquiry.py`、`services/api/app/persistence/repositories/adoption_draft_repository.py`、`services/api/app/persistence/repositories/adoption_inquiry_repository.py` 與最小 migration chain，排除 growth-diary-only schema
- [ ] T022 [US1] semantic merge `services/api/app/api/line_webhook.py`，讓 `start_adoption_matching` 優先進正式領養對話，保留 `X-Line-Signature` 驗證、event idempotency、既有志工照護回報與快速回應行為，刪除公開入口的 adoption placeholder 分支
- [ ] T023 [US1] 確認 `services/api/app/application/adoption_matching_service.py` 與 `services/api/app/persistence/repositories/animal_repository.py` 的每個 animal／organization 查詢都由 server-side organization scope 建立；「推薦我」必須先有 deterministic matching，若依 T006 納入 `services/api/app/application/adoption_ai_analysis_service.py`／`services/api/app/infrastructure/ai/gemini_client.py`，須測試 AI 未設定、timeout、錯誤輸出時自動使用 deterministic fallback，並拒絕 client-supplied organization 越權
- [ ] T024 [US1] 執行 `tests/unit/test_line_adoption_state_machine.py`、`tests/unit/test_line_adoption_draft_service.py`、`tests/unit/test_line_adoption_flex.py`、`tests/integration/test_adoption_conversation_flow.py`、`tests/integration/test_adoption_webhook_flow.py`，並將測試數與結果記錄到 `merge_tasks.md`

**Stop Gate 3 / US1 acceptance**：公開入口恰為兩個 action；正式領養對話可啟動、返回、取消、續接及送出；無 placeholder production path、無跨使用者／跨收容所存取。

## Phase 4：身分型 Rich Menu lifecycle（US2，P0）

**Goal**：志工、已領養者與工作人員只在後端驗證身分後取得對應 menu，返回公開入口不會改變權限。

**Independent Test**：同一 LINE UID 在未綁定、志工核准、志工到期、領養正式完成與工作人員選定收容所等狀態下取得正確 menu；只送出領養申請不得切 adopter menu；menu ID 缺失或 LINE API 失敗不使 webhook crash。

- [ ] T025 [P] [US2] 在 `tests/unit/test_line_role_menu_actions.py` 新增 default／volunteer／adopter／staff／unknown role、missing richMenuId、back-to-default 的 routing matrix，並測試送出 inquiry 不切 adopter menu、只有正式 adoption-completed event 才可切換；若尚無 completion lifecycle 則 adopter auto-switch 必須維持停用
- [ ] T026 [P] [US2] 在 `tests/unit/test_line_volunteer_application_menu.py` 新增志工已核准重入、核准後切 menu、到期後回 default、LINE API failure 不回滾核准結果的測試
- [ ] T027 [US2] semantic merge `services/api/app/application/line_rich_menu_routing.py`，移除把 `PLATFORM_ADMIN` 無條件導向 staff menu 的假設；後端先列出已驗證 memberships，工作人員明確選定目前收容所後才建立 organization-scoped staff menu context，沒有選定收容所時維持 default menu
- [ ] T028 [US2] semantic merge `services/api/app/application/line_menu_actions.py`，讓 `back_to_default_menu` 只切 UI menu、不降權或變更 membership，並移除已由正式 adoption conversation 取代的 `ADOPTION_ENTRY_ACTIONS` placeholder
- [ ] T029 [US2] semantic merge `services/api/app/application/volunteer_access_service.py` 與 `services/worker/app/handlers/volunteer_access_handler.py`，在 transaction 成功後 best-effort 切 volunteer menu，LINE API 失敗只記錄可稽核 warning
- [ ] T030 [US2] semantic merge `services/api/app/application/volunteer_expiration_service.py`，到期後依剩餘有效 membership 決定 menu，不得只憑最後一次 role 或 client 傳入 shelter id
- [ ] T031 [US2] semantic merge `services/api/app/application/authentication/session_service.py` 與 `services/api/app/api/authentication.py`，LINE identity 只作 external identity，綁定時必須驗證邀請／membership，禁止綁定即取得 staff menu
- [ ] T032 [US2] semantic merge `services/api/app/infrastructure/line/messaging_api_adapter.py` 與 `services/api/app/application/ports/line_messaging.py`，確保 client lifecycle、link／unlink、timeout、HTTP error 與 close 行為一致且不洩漏 access token
- [ ] T033 [US2] 執行 `tests/unit/test_line_role_menu_actions.py`、`tests/unit/test_line_volunteer_application_menu.py`、`tests/unit/test_line_adapter_client_lifecycle.py`、`tests/integration/test_volunteer_access_expiration.py`、`tests/integration/test_line_adapter_real_boundary.py` 並將結果記錄到 `merge_tasks.md`

**Stop Gate 4 / US2 acceptance**：身分選單完全由 server-side authorization 決定；Rich Menu 切換失敗不破壞核心交易，且有 log／test 證據。

## Phase 5：工作人員動物 LIFF（US3，P1）

**Goal**：工作人員可由個人 staff menu 開啟動物輸入，但公開使用者、志工與其他收容所 staff 都無法藉 LIFF 或 API 越權。

**Independent Test**：staff A 必須先從後端驗證過的 memberships 選定 shelter A，才能在 shelter A 新增／更新動物；未選定收容所、staff A 對 shelter B、無 membership、過期 session、偽造 client shelter id 均得到拒絕；公開 Rich Menu 不含 staff action。

- [ ] T034 [P] [US3] 在 `tests/integration/test_management_animal_line_input.py` 新增未選定目前收容所、匿名、志工、錯誤 shelter、跨 shelter animal id、偽造 multipart organization、過期 LIFF token 的失敗測試，並測試多 membership 使用者只能操作當次明確選定的收容所
- [ ] T035 [P] [US3] 在 `tests/unit/test_line_staff_animal_input.py` 新增檔案類型／大小、必填欄位、狀態白名單、外部 URL 與 path traversal 的 validation 測試
- [ ] T036 [US3] semantic merge `services/api/app/api/management_animals.py` 與 `services/api/app/application/line_staff_animal_input_service.py`，由 authenticated membership 與 server-validated current-shelter selection 共同產生 shelter scope；沒有選定收容所即 fail closed，且不信任 form/query/body 的 shelter id
- [ ] T037 [US3] 檢查 `services/api/app/main.py` 的 router registration 與 middleware 順序，確保 staff LIFF endpoint 維持既有 authentication、CORS、upload limit 與 error contract
- [ ] T038 [US3] 檢查 `line-liff/staff-animal/js/liff-init.js`、`line-liff/staff-animal/js/api.js`、`line-liff/staff-animal/js/config.js`，不得 hardcode production API／LIFF ID、不得在 localStorage 保存長效 credential、不得由 client 決定 shelter scope
- [ ] T039 [US3] 檢查 `line-liff/staff-animal/js/utils/camera.js` 與 `line-liff/staff-animal/js/utils/validators.js` 的照片尺寸、MIME、取消拍照、重送與錯誤回饋，後端仍須重做同等 validation
- [ ] T040 [US3] 更新 `specs/001-volunteer-care-report/contracts/openapi.yaml` 的 staff animal contract，並確認所有 frontend/API consumers 與 `packages/contracts/src/openapi.ts` 是否需要同步生成或明確排除
- [ ] T041 [US3] 執行 `tests/unit/test_line_staff_animal_input.py`、`tests/integration/test_management_animal_line_input.py`、`tests/integration/test_management_animals.py`、`tests/integration/test_management_workbench_api_boundaries.py` 並記錄 tenant-isolation 結果到 `merge_tasks.md`

**Stop Gate 5 / US3 acceptance**：staff menu 不公開；UI 隱藏以外，API/service/repository 三層均有可測試的 shelter authorization。

## Phase 6：DB、migration 與 async worker 安全

**目的**：新增 adoption schema 與 lifecycle handler 不得破壞 demo/test DB 邊界或 GCE worker runtime。

- [ ] T042 [P] 對 `services/api/migrations/versions/` 執行 `uv run alembic heads`，確保整合後只有預期 head；若出現多 head，新增只合併 revision graph 的 migration，不改寫既有已發布 migration
- [ ] T043 在全新 `strayhub_test` 或符合 narrow ephemeral exception 的 scratch DB 執行 upgrade head／downgrade review／再 upgrade，驗證 adoption tables、FK、index、tenant key 與既有資料相容性，結果記錄到 `merge_tasks.md`
- [ ] T044 [P] 執行 `tests/unit/test_test_database_safety.py` 與所有 DB isolation／fixture guard contract，證明 demo=`strayhub`、test=`strayhub_test`、ephemeral exception、production rejection 均維持 fail-closed
- [ ] T045 掃描 `scripts/demo-line.sh`、`scripts/adoption_chat_demo.py`、`scripts/sync_line_role_menus.py`、`scripts/bind_line_account.py`、`line-liff/` 是否引用 ORG-A、local fixture identity、`scripts.seed_local` 或 demo DB 測試寫入，將每個命中與處置記錄到 `merge_tasks.md`
- [ ] T046 semantic merge `services/worker/worker.py` 與 `services/worker/app/handlers/volunteer_access_handler.py`，只註冊 T006 核准範圍所需 handler，排除 Growth Diary handler 與所有未列入 dependency-closure manifest 的 AI background job
- [ ] T047 [P] 測試 worker import、async DB session lifecycle、volunteer expiration、重試與 shutdown，執行 `tests/integration/test_volunteer_access_expiration.py` 及核准範圍內 handler tests
- [ ] T048 檢查 webhook 與 worker 的外部 side effect ordering，確保 DB transaction／idempotency key 成功後才送 LINE menu switch，重試不會重複建立 adoption inquiry 或跨 tenant 寫入
- [ ] T049 將 Demo DB boundary、Test DB isolation、Fixture mutation safety、Ephemeral exception、Unsafe entry points 五項證據與 PASS／FAIL 記錄到 `merge_tasks.md`

**Stop Gate 6**：五項 DB safety 全部 PASS、migration 可由乾淨 DB 重建、worker async regression 無 failure。

## Phase 7：Runtime config 與 GCE production contract（US4，P0）

**Goal**：LINE local demo 可配置，但不使 production 接受 mock LIFF、空白安全設定、測試資料或 repository credential。

**Independent Test**：local 缺少 role menu ID 時 webhook graceful no-op；production 部署後新 LINE 功能預設停用，只有明確 enable 且 secrets、IDs、preflight、真實 smoke 齊備才可啟用；缺少任何必要設定時 fail closed；mock／placeholder URL 無 production route。

- [ ] T050 [P] [US4] 建立 LINE env inventory，逐項標記 secret／non-secret、API／worker／web consumer、local default、production requiredness、Secret Manager key 與 production enable flag；enable flag 預設關閉並記錄於 `docs/deployment/production-config-contract.md`
- [ ] T051 [US4] 同步 `infra/gce/.env.production.example`、`infra/gce/.env.production.template`、`infra/gce/secrets/production-secret-map.tsv` 與 `infra/gce/docker-compose.production.yml`；只加入實際 production 必需的 LINE 變數，禁止 fake value 被 production 接受
- [ ] T052 [US4] 更新 `infra/gce/scripts/preflight.sh`、`infra/gce/scripts/production-preflight.sh` 與 `tests/contract/test_gce_secret_manager_contract.py`，驗證 production 預設停用；只有明確 enable 時才要求並驗證 credential、public URL、menu IDs、LIFF IDs 與已完成真實 smoke 的 release evidence，缺一即 fail closed
- [ ] T053 [US4] 檢查 `apps/web/public/adoption-entry/index.html`、`line-liff/adopter/index.html` 與 `_adoption_entry_message` placeholder；正式 adoption conversation 上線後刪除 production route，若保留 demo 必須以 local-only flag 與 production contract 明確拒絕
- [ ] T054 [P] [US4] 驗證 `infra/gce/nginx/strayhub.conf` 只暴露核准 API/web path，不為 local-only `line-liff/serve-demo.sh` 或 mock static page 新增 production alias
- [ ] T055 [P] [US4] 驗證 `infra/gce/systemd/`、`scripts/build-release-bundle.sh`、`infra/gce/images/Dockerfile.api`、`Dockerfile.worker`、`Dockerfile.web` 的 env loading、asset packaging 與最小權限沒有因 LINE 內容退化
- [ ] T056 [US4] 執行所有 `tests/contract/test_gce_*.py`、`tests/contract/test_single_edge_nginx_contract.py`、production compose config、shell syntax、Terraform validate 與 release bundle contract，結果記錄到 `merge_tasks.md`
- [ ] T057 [US4] 執行 secret scan 與 tracked-file inspection，證明 LINE channel secret、access token、LIFF credential、ngrok URL、production DB URL、KMS material 均未進入 Git，結果記錄到 `merge_tasks.md`

**Stop Gate 7 / US4 acceptance**：GCE compose、nginx、systemd、Secret Manager、KMS、backup/restore、release/rollback、preflight 全部 PASS；mock LIFF 無 production path。

## Phase 8：完整 regression 與人工 LINE smoke

**目的**：先跑 focused tests，再跑全套；所有 failure 必須分類處理，不得 skip 或放寬 assertion。

- [ ] T058 [P] 執行 LINE focused suite：`tests/unit/test_line_*.py`、`tests/integration/test_line_*.py`、`tests/integration/test_adoption_webhook_flow.py`、`tests/integration/test_management_animal_line_input.py`、`tests/integration/test_volunteer_access_expiration.py`，結果記錄到 `merge_tasks.md`
- [ ] T059 [P] 執行 authentication／authorization／tenant isolation focused suite，涵蓋 `tests/unit/test_liff_exchange_states.py`、management boundary tests 與所有 `isolation`／`security` marker，結果記錄到 `merge_tasks.md`
- [ ] T060 執行完整 Python gate：`uv run ruff check .`、`uv run ruff format --check .`、使用專用 `strayhub_test` 的 `uv run pytest`；結果必須至少不低於原 baseline `1097 passed, 2 skipped, 0 failed` 且所有新增測試通過
- [ ] T061 [P] 執行 web gate：`npm --prefix apps/web run quality` 與 `npm --prefix apps/web run build`，確認 API contract／TypeScript consumer／LIFF asset packaging 無 regression
- [ ] T062 執行 `./scripts/verify_local.sh` 與 CI 等價 critical e2e，確認 normal demo database/storage guard、demo bootstrap、login、management、volunteer 與 DB isolation 都通過
- [ ] T063 [P] 以缺少全部 `LINE_RICH_MENU_*_ID`、只缺單一 role ID、Messaging API 5xx／timeout 三種情境驗證 webhook 仍快速回覆且不 crash，結果記錄到 `merge_tasks.md`
- [ ] T064 使用 local-only credential 執行 `scripts/demo-line.sh` smoke：公開 menu → 志工申請 → 管理員核准 → 自動切 volunteer menu → 返回公開 menu → 領養流程 → 選地區／收容所 → 分別完成「心有所屬」與 AI 停用時的「推薦我」→ 返回／取消／續接；送出 inquiry 後確認未切 adopter menu
- [ ] T065 使用真實 LINE account、公開 HTTPS tunnel、LIFF ID 與 Messaging API credential 執行 staff smoke：後端驗證 memberships → 工作人員選定目前收容所 → 授權該收容所 staff menu → 新增動物 → 更新健康／照片 → 動物清單；切換收容所必須重新建立 context，並驗證未選定收容所與非 staff 都無法重播相同 LIFF/API request
- [ ] T066 測試志工到期與多 membership 邊界：一個 shelter 到期不得移除另一 shelter 權限，menu context 不得暴露另一 shelter 動物，結果記錄到 `merge_tasks.md`
- [ ] T067 測試 duplicate webhook／重試／LINE reply token 失效／menu link failure，確認 adoption draft、inquiry、animal mutation 與 approval 都具冪等或安全失敗行為
- [ ] T068 以 `git diff origin/main...HEAD` 審核所有變更，確認 T006 標記 EXCLUDED 的 Growth Diary、非領養用途 Gemini、非必要 adoption admin UI、CI rewrite 與文件未意外進入 integration diff
- [ ] T069 執行 `git diff --check`、搜尋 conflict marker、搜尋 credential pattern、列出 untracked files，將 clean evidence 記錄到 `merge_tasks.md`

**Stop Gate 8**：focused、full Python、web、local verification、LINE smoke 全部有證據；任一 failure 皆為 blocker。

## Phase 9：文件、PR 與最終 readiness

- [ ] T070 [P] 更新 `docs/line-role-menu-framework.md`，記錄公開兩入口、身分 menu 狀態圖、missing-ID no-op、back-to-default 不改權限與正式 adoption action
- [ ] T071 [P] 更新 `docs/line-account-setup.md` 與 `docs/staff-animal-line-input.md`，區分 local demo／test／production credential、真實 LINE／LIFF smoke 前置條件與 staff server-side authorization
- [ ] T072 更新 `README.md` 與 `.env.example` 最終操作說明，確認不把 fixture seed、ORG-A 或 `strayhub_test` 流程描述成 normal demo
- [ ] T073 在 `merge_tasks.md` 填寫最終報告：Status、integration HEAD、main base、role source、adoption source/scope manifest、unresolved conflicts、CI、full Python、LINE regression、DB boundary、GCE contract、production impact、known limitations
- [ ] T074 只有當所有 Stop Gates PASS 時才將 status 設為 `MERGE_READY`；否則設為 `NOT_MERGE_READY` 並列出 blocker owner、重現方式與下一步
- [ ] T075 在取得明確授權後建立 integration PR 回 `main`，PR 內容附 conflict ledger、T006 scope manifest、validation evidence、rollback strategy，合併方法指定 `MERGE_COMMIT` 且不得自動 merge
- [ ] T076 PR head 或 main head 若在 review 期間移動，重新執行 T001–T006 與所有受影響 gates；未再次通過不得核准或 merge

## 依賴與建議執行順序

```text
Phase 1 基線鎖定
  → Phase 2 role branch semantic merge
    → Phase 3 公開入口＋正式領養（US1）
      → Phase 4 身分 menu lifecycle（US2）
        → Phase 5 staff LIFF（US3，屬於已確認 role branch 範圍）
          → Phase 6 DB／worker
            → Phase 7 production contract（US4）
              → Phase 8 full regression／真實 LINE smoke
                → Phase 9 PR readiness
```

- T005 與 pre-merge baseline 中互不寫檔的 inventory／測試可平行。
- US1 測試、US2 測試、US3 authorization 測試可先在不同測試檔平行撰寫，但 `line_webhook.py`、`settings.py`、`management_animals.py` 的 semantic merge 必須序列化。
- GCE 靜態 contract、web quality 與 focused Python tests 可平行；full pytest 與使用同一 test DB 的 migration test 不可共用資料庫平行執行。
- 真實 LINE smoke 必須在 local/static gates 全部通過後執行，且只使用非 production 資料與 credential。

## 最小可交付範圍

最小可驗收增量是 Phase 1–4：公開兩入口、正式領養 LINE 對話、志工 lifecycle 與安全的 menu routing；但本次方案 2 的完整 `MERGE_READY` 仍要求 Phase 5–9 全部通過。由於 staff LIFF 已包含在完整整合的 role branch 中，若 authorization／tenant-isolation gate 未完成，本輪狀態必須是 `NOT_MERGE_READY`，不得只靠隱藏 menu 或保持 UI 不可達就合併。

## 回滾策略

1. integration 過程失敗：abort 尚未完成的 merge，或直接捨棄臨時 integration branch；`main` 不受影響。
2. PR review 發現 blocker：不 merge，修正在 integration branch 後重跑受影響 gate。
3. integration PR 已 merge 但尚未部署：以新的 revert PR 回復該 merge commit，不改寫 `main` 歷史。
4. 已部署才發現問題：先使用既有 GCE immutable release rollback 回上一個已驗證 revision，再建立 revert/fix PR；不得手改 production DB 或 secrets。
5. migration 已套用：依 migration/data compatibility review 決定 roll-forward 或經核准的 downgrade；不得任意 drop production table。任何 schema rollback 必須先備份並驗證 restore。

## 完成判定

只有在 T001–T076 全部完成、所有 Stop Gates 為 PASS、T006 manifest 證明未超出方案 2、工作目錄無無關變更，且最終報告為 `MERGE_READY` 時，才可建議將 integration PR 合併到 main。任何範圍刪減或擴張都必須先修訂本文件並取得明確核准；真正 merge main 仍需另一次明確授權。
