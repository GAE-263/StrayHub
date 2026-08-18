# Quickstart: 收容所管理員人數與權限調整確認

## 目的

驗證每個收容所啟用中的 `SHELTER_ADMIN` 維持一至兩位，且權限異動必須經確認 Modal；成功後左下角出現 Toast，失敗或取消不會出現成功通知。

## 前置條件

1. PostgreSQL 已啟動，或使用專案既有本機環境。
2. 重新建立／更新本機展示資料並啟動 API 8001、Web 3001：

   ```bash
   DEMO_SKIP_DOCKER=1 ./scripts/demo.sh
   ```

3. 開啟 [http://127.0.0.1:3001/login](http://127.0.0.1:3001/login)。本機展示帳號密碼均為 `local-only-password`：

   | Account | Scope | Purpose |
   |---|---|---|
   | `local-shelter-admin-a` | ORG-A `SHELTER_ADMIN` | 主要操作與 Modal／Toast 驗收 |
   | `local-staff-a` | ORG-A `STAFF` | 被調整的工作人員候選 |
   | `local-volunteer-a` | ORG-A `VOLUNTEER` | 驗證志工角色與授權狀態不被繞過 |
   | `local-platform-admin` | Platform `PLATFORM_ADMIN` | 建立測試帳號及切換收容所 |

## 手動驗收

### 1. 一位管理員時不可移除最後權限

1. 使用 `local-shelter-admin-a` 登入，前往 `/shelters`，確認目前啟用中的 `SHELTER_ADMIN` 為一位。
2. 對唯一管理員嘗試停用、改成 `STAFF` 或封存。
3. 確認先出現確認 Modal；取消時資料不變。
4. 再次確認後，操作應被拒絕，顯示「至少需要一名」類似原因；不要出現成功 Toast，管理員仍為啟用中。

### 2. 兩位管理員時不可新增第三位

1. 在只有一位管理員的 ORG-A，以 `建立帳號` 建立一個新的 `STAFF` 測試帳號。
2. 對新帳號選擇 `SHELTER_ADMIN`，確認 Modal 應顯示管理員數量 `1 → 2`；確認後左下角顯示完成角色調整的 Toast。
3. 再建立另一個 `STAFF` 測試帳號，嘗試提升為 `SHELTER_ADMIN`，確認 Modal 應顯示 `2 → 3` 的風險。
4. 確認後 API 應拒絕，清單仍為兩位管理員，且沒有成功 Toast。

### 3. Modal 取消與各種成功 Toast

1. 對工作人員執行角色、醫療資料權限、停用或重新啟用操作，確認每次都先顯示 Modal。
2. 以取消、關閉按鈕與 Escape 各測一次，確認沒有 API mutation、資料沒有變化、沒有成功 Toast。
3. 確認一次有效變更，檢查左下角 Toast 同時包含完成動作與姓名／帳號，而不是只顯示 UUID。
4. 檢查 Toast 不包含密碼、醫療資料內容或跨收容所資料。
5. 開啟瀏覽器 Performance 記錄，在按下確認的時間點記下 `t0`；以畫面出現 Toast 的時間 `t1` 計算 `t1 - t0`，每種操作至少測一次，必須小於或等於 2 秒。若 API 失敗或版本衝突，應確認不出現成功 Toast。

### 4. 封存／恢復管理員

1. 在兩位管理員時封存其中一位，確認 Modal 顯示 `2 → 1`，成功後顯示封存 Toast。
2. 到 `/shelters/archived`，對該管理員執行恢復；確認 Modal 顯示 `1 → 2`，成功後恢復清單資料。
3. 在已有兩位管理員時，對第三個已封存管理員執行恢復；確認被拒絕、不顯示成功 Toast，且仍留在封存頁。

### 5. 租戶隔離與狀態語意

1. 以平台管理員切換 ORG-A／ORG-B，確認每個收容所各自計算一至兩位，ORG-A 的異動不改變 ORG-B。
2. 對志工 `expired`／`revoked` 狀態嘗試重新啟用，確認沿用既有志工授權錯誤，不會因確認 Modal 直接恢復有效志工權限。

### 6. 使用者理解度驗收（SC-008）

準備同一份包含管理員、工作人員、志工及停用歷史的展示資料，邀請 5 位未參與開發的管理者個別完成以下任務：開啟 `/shelters`、說出目前啟用中管理員人數、確認一次合法異動後說出異動後人數，並指出 Toast 的動作與目標。每位限時 30 秒，不提供操作提示；將完成／未完成、耗時與觀察記錄到 `specs/010-shelter-admin-governance-confirmation/validation/usability-test-plan.md`。至少 4 位完成四項辨識才算 SC-008 通過。

## 自動化驗證

後端：

```bash
uv run pytest \
  tests/unit/test_organization_management_service.py \
  tests/integration/test_organization_management.py \
  tests/contract/test_organization_management_contract.py \
  tests/contract/test_volunteer_access_contract.py \
  tests/integration/test_volunteer_access_approval.py \
  tests/unit/test_volunteer_grant_mutation.py
```

前端元件與型別：

```bash
npm --prefix apps/web run test -- \
  'app/(management)/shelters/page.test.tsx' \
  'app/(management)/shelters/archived/page.test.tsx' \
  'features/volunteer-access/AccessGrantTable.test.tsx' \
  'features/volunteer-access/ApplicationBatchWorkbench.test.tsx' \
  'components/management/MembershipPermissionDialog.test.tsx' \
  'components/ui/toast.test.tsx'
npm --prefix apps/web run typecheck
```

管理流程 E2E（API／Web 已在 8001／3001 啟動時）：

```bash
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 \
PLAYWRIGHT_SKIP_WEBSERVER=1 \
npm --prefix apps/web run test:e2e -- e2e/organization-management.spec.ts e2e/volunteer-access-approval.spec.ts
```

完成標準：所有上下限邊界、Modal 取消／確認、成功／失敗 Toast、封存／恢復、跨收容所隔離與志工狀態案例均通過；Python 變更另須通過 `ruff check .`、`ruff format --check .` 與完整 `pytest`。

## 驗收紀錄

- 後端 feature unit／integration／contract：40 passed（另含 API audit 與收容所鎖定並發案例）。
- 後端完整 pytest：474 passed。
- 前端 feature Vitest：4 個 test files、8 tests passed；TypeScript typecheck passed。
- 前端完整 Vitest／mobile／a11y：各 50 個 test files、97 tests passed；TypeScript typecheck passed。
- 管理流程 Playwright：8 passed（`organization-management.spec.ts`、`volunteer-access-approval.spec.ts`）。
- 全域 `ruff check .`／`ruff format --check .`：passed；前端本次修改檔案已通過 Prettier。
- `apps/web` 全域 format check 仍有既有的 `e2e/animal-medical-timeline.spec.ts`、`e2e/care-agenda-real.spec.ts` 格式警告，未納入本 feature 修改。
- SC-008 五位管理者理解度測試：待人工執行，紀錄模板位於 `validation/usability-test-plan.md`。
