# Quickstart: 平台管理員人數與替換治理

## Prerequisites

- Repository root: `/Users/js/gae_cowork_project/StrayHub`
- API、PostgreSQL 與 frontend 已啟動；本機 API 使用 `http://127.0.0.1:8001`，frontend 使用 `http://127.0.0.1:3001`
- Migration 已套用，local seed 已執行
- `local-platform-admin` / `local-only-password`
- 目前 local seed 預期有一位啟用中的平台管理員與一位已停用的平台管理員；`local-shelter-admin-a` 是 ORG-A 的 `SHELTER_ADMIN`，不是平台管理員

## Standard Local Fixture

SC-006 的 Standard Local Fixture 固定包含：2 位平台管理員（1 位啟用中、1 位已停用）、1 個無志工歷史的可提升 active User、3 位分別具有 active／expired／revoked Membership 歷史的 active Users，以及 3 位分別具有 rejected／withdrawn／pending VolunteerApplication 歷史的 active Users。其中 revoked fixture 必須是 `role=VOLUNTEER`、`status=revoked` 的 `OrganizationMembership`，不以 `VolunteerAccessGrant` 另建角色來源。驗收不以志工目前是否仍可使用為條件；只要存在任一志工 Membership 或申請紀錄，就不得出現在提升候選清單。

## Scenario 1: 查看全域平台治理摘要

1. 以 `local-platform-admin` 登入並開啟 `http://127.0.0.1:3001/platform-admins`。
2. 確認頁面不要求先選擇收容所。
3. 確認顯示啟用中人數 `1`、最少 `1`、最多 `2`、剩餘名額 `1`。
4. 確認清單顯示姓名與帳號；`local-shelter-admin-a` 不因 ORG-A 的 `SHELTER_ADMIN` Membership 出現在平台管理員清單。
5. 確認已停用的平台管理員卡片使用偏灰樣式，且可執行「重新啟用」。

## Scenario 2: 最後一位管理員保護

1. 在只有一位啟用中平台管理員時，嘗試停用或降權目前管理員。
2. 確認操作回應 `409 last_platform_admin`，畫面說明至少要保留一位啟用中的平台管理員。
3. 重新整理清單，確認該帳號仍為啟用中的平台管理員，且沒有成功異動事件。
4. 查詢平台稽核，確認拒絕事件包含操作者、目標、操作與原因。

## Scenario 3: 兩位上限

1. 建立或提升一個符合條件的啟用帳號。
2. 確認 `local-volunteer-a`、`local-volunteer-state-expired`、`local-volunteer-state-rejected`、`local-volunteer-state-revoked` 與 `local-applicant-all-filtered-0001` 都不在「提升既有帳號」候選清單中。
3. 確認摘要變成 `2 / 2`，一般新增、提升與啟用控制項不再允許增加第三位。
4. 嘗試建立第三位，確認回應 `409 platform_admin_limit_reached`，既有兩位角色與目標帳號資料不變。

## Scenario 4: 管理員替換

1. 在已有兩位啟用中平台管理員的狀態，選擇一位 active、尚未具備平台管理員角色的非平台帳號作為 replacement。
2. 指定 outgoing admin 與 replacement user，輸入交接原因並確認。
3. 確認新帳號成為平台管理員、原帳號不再具備平台角色，摘要仍為 `2 / 2`。
4. 確認替換失敗時（例如 replacement 已停用）新舊角色均保持原狀。
5. 查詢平台稽核，確認替換事件共用 operation id，且包含新舊帳號、前後狀態、操作者與原因。
6. 嘗試以具有 expired、revoked Membership、rejected、withdrawn 或 pending 志工歷史的帳號作為 replacement，確認後端回應 `409 platform_admin_replacement_invalid`，且新舊帳號角色均不變；此後端驗收由 T055 負責，T056 只負責 revoked fixture 與候選清單文件同步。

## Scenario 5: 平台角色與收容所 Membership 分離

1. 以 `local-shelter-admin-a` 登入並嘗試開啟 `/platform-admins`。
2. 確認收到既有平台管理員拒絕，不因 ORG-A 的 `SHELTER_ADMIN` Membership 取得平台管理頁。
3. 以平台管理員修改一個帳號的 platform role，確認其既有收容所 Membership role 與 status 不被連帶修改。

## Scenario 6: 並發與失敗安全

1. 同時送出兩個將不同帳號提升為第三位平台管理員的請求。
2. 確認最多一個請求成功，最終啟用中的平台管理員數量不超過兩位。
3. 同時送出可能停用最後一位管理員的請求，確認至少一個請求被拒絕，最終數量不低於一位。
4. 替換任一階段失敗後，確認沒有只完成新角色或只清除舊角色的部分狀態。

## Scenario 7: Migration 與 bootstrap

1. 在全新空資料庫執行 `uv run alembic upgrade head`。
2. 執行 `uv run python -m scripts.seed_local`，確認建立一位啟用中的 `local-platform-admin`。
3. 在已有 User 資料但啟用平台管理員數量為 0 或超過 2 時執行 Migration，確認 Migration fail closed 並提供修復提示。

## Automated validation

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/unit/test_platform_admin_management_service.py tests/contract/test_platform_admin_management_contract.py
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/integration/test_platform_admin_governance.py tests/security/test_platform_admin_governance.py
env UV_CACHE_DIR=/tmp/uv-cache uv run ruff check services/api/app/api/platform_admin_management.py services/api/app/application/platform_admin_management.py services/api/app/persistence/repositories/platform_admin_repository.py
env UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check services/api/app/api/platform_admin_management.py services/api/app/application/platform_admin_management.py services/api/app/persistence/repositories/platform_admin_repository.py
npm --prefix apps/web run test -- app/\\(management\\)/platform-admins/page.test.tsx
npm --prefix apps/web run typecheck
PLAYWRIGHT_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001 npm --prefix apps/web run test:e2e -- e2e/platform-admin-governance.spec.ts
```

本次實作驗證結果：完整 Pytest `464 passed`、完整 Ruff `check .` 通過、完整 Ruff format check `503 files already formatted`；Vitest `48 files / 94 tests passed`、TypeScript 通過、OpenAPI generated contract check 通過；平台治理瀏覽器驗收 `1 passed`，並以沒有 Active Shelter Context 的平台管理員情境驗證。平台治理相關檔案的 Prettier check 通過；全域 frontend format check 仍會列出既有且不屬於本 Feature 的其他檔案，未在本次範圍內改動。
