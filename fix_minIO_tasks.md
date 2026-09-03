# 管理後台毛孩圖片存取修復任務

## 目標

修復管理後台毛孩清單與毛孩詳細頁在 ngrok／外部瀏覽器無法顯示圖片的問題。後端不得再把私人 MinIO 的 `127.0.0.1:9000` signed URL 交給瀏覽器，而應透過具備登入驗證與收容所隔離的 API 端點提供圖片。

## 已確認根因

- 毛孩圖片物件存在於私人 MinIO。
- `ManagementAnimalService` 目前產生 `http://127.0.0.1:9000/...` signed URL。
- 外部瀏覽器會把 `127.0.0.1` 解讀成使用者自己的裝置，因此無法取得圖片。
- 管理端 access token 位於 `sessionStorage`，直接使用 `<img src="/v1/...">` 不會附加 `Authorization` header；前端必須使用 `authFetch()` 取得 Blob。
- 本機資料盤點結果為 126 筆有圖片的動物全部都有可信任的 `media_assets` 紀錄，目前不需要 migration。

## 固定設計決策

1. 新增 `GET /v1/management/animals/{animal_id}/photo`。
2. 允許 `STAFF`、`SHELTER_ADMIN`、已選定收容所 context 的 `PLATFORM_ADMIN` 存取。
3. 動物、圖片 metadata 與 object key 必須由後端依目前 `organization_id` 查詢，不信任 client 傳入的 shelter ID。
4. 跨收容所、無圖片、metadata 不可信或 storage object 不存在，一律回傳不洩漏資源狀態的 `404`。
5. 圖片只允許 `image/jpeg`、`image/png`、`image/webp`，且 `MediaAsset.status == "processed"`、`exif_removed == true`。
6. `ManagementAnimal.photo_url` 保持 `string | null`，有圖時改回傳同源相對路徑，不做 breaking rename。
7. 前端透過 `authFetch()` 下載 Blob，再使用 `URL.createObjectURL()` 顯示，並在卸載、換圖與切換收容所時撤銷 object URL。
8. MinIO 維持私人；不新增公開 port、第二條 ngrok tunnel、公開 bucket 或 hostname 字串替換。
9. 不修改 Docker、Terraform、Nginx、LINE 公開領養圖片或 Growth Diary 功能。
10. 本次不新增資料表或 migration；只有目標環境盤點發現 metadata 缺口時，才另外規劃資料修復。

## User Stories

### US1 — 管理者安全取得毛孩圖片（P1）

已登入且具有管理權限的使用者，可以透過同源 API 取得目前收容所毛孩的可信任圖片；不能取得其他收容所圖片。

**獨立驗收**：直接呼叫圖片端點，確認合法角色取得正確圖片 bytes 與 headers，跨 tenant 與不可信圖片回 `404`。

### US2 — 管理後台正確顯示圖片（P1）

管理者在毛孩清單與詳細頁都能看到圖片；載入失敗時顯示 placeholder，且頁面、DOM、JSON 與 Network request 不出現私人 MinIO URL。

**獨立驗收**：以 mocked API 完成 frontend unit/E2E，確認 Bearer fetch、Blob lifecycle、清單與詳細頁顯示。

### US3 — ngrok 與 GCP 部署路徑可用（P1）

外部瀏覽器只透過公開 Web origin 的 `/v1/.../photo` 讀取圖片，由 API 在內部存取 MinIO；不需要公開 MinIO。

**獨立驗收**：在本機與 ngrok 完成真實圖片請求，再以 production-like proxy 設定驗證同一流程。

## Phase 1：Setup 與範圍凍結

- [ ] T001 記錄修復前的 `git status --short --branch`、`git diff --stat` 與目前 commit SHA，確認 working tree 中是否存在不屬於本功能的變更
- [ ] T002 在瀏覽器 Network 或可重複診斷測試中保存失敗證據：管理動物 JSON 的 `photo_url` 指向 `127.0.0.1:9000`，且 ngrok 頁面圖片請求失敗
- [ ] T003 在 `services/api/app/application/management_animal_service.py`、`services/api/app/api/management_animals.py`、`apps/web/app/(management)/animals/page.tsx` 與 `apps/web/features/animal-management/AnimalBasicProfile.tsx` 確認目前資料流與所有本功能 consumer
- [ ] T004 只讀盤點目標環境中 `animals.current_photo_key` 與 `media_assets` 的 tenant、status、EXIF、MIME 一致性；若有缺口，停止實作並另外提出資料修復清單

## Phase 2：Foundational contract 與紅燈測試

**Gate**：T005–T008 必須先產生預期紅燈，確認測試確實能捕捉目前問題；不得先改 production code 再補測試。

- [ ] T005 [P] 在 `tests/contract/test_animal_profile_contract.py` 新增圖片端點 contract 測試，要求 Bearer security、200 binary image response、401／403／404／409 與安全 headers
- [ ] T006 [P] 在 `tests/integration/test_management_animals.py` 新增 service 回歸測試，要求 `photo_url` 為 `/v1/management/animals/{animal_id}/photo`，且不得包含 `127.0.0.1`、MinIO bucket 或 query signature
- [ ] T007 [P] 在 `tests/integration/test_animal_profile_api.py` 或新的 focused integration test 新增角色與 tenant isolation 紅燈案例
- [ ] T008 [P] 在 `apps/web/features/animal-management/AnimalBasicProfile.test.tsx` 與毛孩清單測試中新增 authenticated Blob 顯示、錯誤 fallback、abort 與 object URL 清理紅燈案例

## Phase 3：US1 — 後端安全圖片端點

- [ ] T009 [US1] 在 `services/api/app/application/management_animal_service.py` 增加輕量圖片 descriptor，沿用 service 既有直接、tenant-scoped SQLAlchemy 查詢方式，不建立只供單一 endpoint 使用的新 repository abstraction
- [ ] T010 [US1] 在 `services/api/app/application/management_animal_service.py` 以同一查詢限制 `Animal.id`、`Animal.organization_id`、`MediaAsset.organization_id` 與 current object key 關聯，避免跨 tenant 或同名 key 誤配
- [ ] T011 [US1] 在 `services/api/app/application/management_animal_service.py` 驗證 current photo、processed、EXIF removed 與 JPEG／PNG／WebP allowlist；不得額外要求 purpose 或 subject
- [ ] T012 [US1] 在 `services/api/app/application/management_animal_service.py` 將清單與詳細資料的 `photo_url` 改成同源相對 API endpoint，並移除每筆資料產生 MinIO signed URL 的行為
- [ ] T013 [US1] 在 `services/api/app/api/management_animals.py` 新增 `GET /{animal_id}/photo`，沿用 `current_request_context`、`request_session` 與 `require_staff_or_admin`
- [ ] T014 [US1] 在 `services/api/app/api/management_animals.py` 透過 `MinioStorageAdapter.get(scope=ObjectScope(organization_id), key=...)` 讀取私人圖片，不接受 client 傳入 object key 或 organization ID
- [ ] T015 [US1] 在 `services/api/app/api/management_animals.py` 回傳可信任的實際 MIME type，並設定 `Cache-Control: private, no-store` 與 `X-Content-Type-Options: nosniff`
- [ ] T016 [US1] 在 `services/api/app/api/management_animals.py` 將 storage object 不存在或讀取失敗轉成一致的安全 `404`，並以 module logger 保留 server-side exception evidence；不得把 endpoint、bucket、object key 或 exception message 回傳給 client
- [ ] T017 [US1] 在 `specs/001-volunteer-care-report/contracts/openapi.yaml` 補上管理毛孩圖片 endpoint 與 operation ID，維持 `ManagementAnimal.photo_url` 為 nullable string
- [ ] T018 [US1] 執行 `npm --prefix packages/contracts run generate` 更新 `packages/contracts/src/openapi.ts`，再執行 `npm --prefix packages/contracts run check`
- [ ] T019 [US1] 執行 T005–T007 的 backend targeted tests，確認合法角色、錯誤狀態、tenant isolation、MIME 與 headers 全部轉綠

## Phase 4：US2 — 前端 authenticated image 顯示

- [ ] T020 [US2] 在 `apps/web/features/animal-management/AnimalPhoto.tsx` 建立 feature-scoped 圖片元件，使用 `authFetch(photoUrl, { signal })` 取得 Blob
- [ ] T021 [US2] 在 `apps/web/features/animal-management/AnimalPhoto.tsx` 實作 loading、ready、error 狀態與 `URL.createObjectURL()`／`URL.revokeObjectURL()` lifecycle
- [ ] T022 [US2] 在 `apps/web/features/animal-management/AnimalPhoto.tsx` 處理 component unmount、photo URL 改變與 request abort，並依賴既有 `authFetch`／`OrganizationRequestScope` 的 context-switch stale-body protection；不得建立第二套 shelter-switch listener
- [ ] T023 [US2] 在 `apps/web/features/animal-management/AnimalBasicProfile.tsx` 以 `AnimalPhoto` 取代直接 `<img src={animal.photo_url}>`，保留現有 alt text、尺寸與失敗 fallback
- [ ] T024 [US2] 在 `apps/web/app/(management)/animals/page.tsx` 以 `AnimalPhoto` 取代清單直接 `<img>`，保留既有縮圖版面與沒有圖片時的行為
- [ ] T025 [P] [US2] 在 `apps/web/features/animal-management/AnimalPhoto.test.tsx` 驗證 Authorization-aware fetch、Blob 顯示、abort、換圖與 object URL revoke
- [ ] T026 [P] [US2] 更新 `apps/web/features/animal-management/AnimalBasicProfile.test.tsx`，驗證圖片成功、404／503 fallback 與頁面其餘資料不受影響
- [ ] T027 [P] [US2] 更新或新增毛孩清單 component/E2E 測試，驗證多筆縮圖、無圖項目與單張失敗不影響其他列
- [ ] T028 [US2] 執行 animal-management frontend unit tests、TypeScript typecheck、lint 與 build，確認沒有未撤銷 object URL 或型別退化

## Phase 5：US3 — 真實路徑與部署驗證

- [ ] T029 [US3] 啟動本機 Postgres、MinIO、API `8001` 與 Web `3001`，確認 health check 與 API proxy 正常
- [ ] T030 [US3] 在本機管理後台驗證毛孩清單與指定毛孩詳細頁圖片，確認 Network 只請求 `/v1/management/animals/{id}/photo`
- [ ] T031 [US3] 使用 `https://radar-legwarmer-squint.ngrok-free.dev/animals/8923fb4c-c18f-5a80-8139-2b2b680e6a22` 或當次有效 ngrok URL 實測圖片顯示
- [ ] T032 [US3] 在 ngrok 實測中確認 HTML、JSON、DOM 與 Network 不含 `127.0.0.1:9000`、MinIO hostname、bucket 名稱或 signed query parameters
- [ ] T033 [US3] 以 STAFF、SHELTER_ADMIN、PLATFORM_ADMIN 各驗證一次；PLATFORM_ADMIN 必須先選定 active shelter context
- [ ] T034 [US3] 切換到另一個 shelter context，確認舊 Blob 立即撤銷，原 shelter 圖片不可讀且 API 回 `404`
- [ ] T035 [US3] 在 production-like Web/API proxy 設定下驗證瀏覽器只連公開 origin、API 可連私人 MinIO，確認不需要修改 Docker、Nginx、Terraform 或 GCP firewall
- [ ] T036 [US3] 若可連線到實際 GCP 環境，先只讀執行 T004 的 metadata 一致性盤點，再於非破壞性帳號與資料範圍執行 smoke test

## Phase 6：Polish、完整品質門檻與交付

- [ ] T037 [P] 對所有實際修改的 Python 檔案執行 targeted Ruff check／format check 與 mypy
- [ ] T038 [P] 對所有實際修改的 TypeScript／TSX 檔案執行 targeted lint、unit test 與 typecheck
- [ ] T039 執行 `git diff --check`，確認沒有 trailing whitespace、CRLF 或 patch 格式問題
- [ ] T040 執行 backend 圖片 contract、integration、tenant isolation 與 storage failure targeted tests
- [ ] T041 執行 frontend animal management unit tests 與相關 Playwright E2E
- [ ] T042 執行完整 `./scripts/verify_local.sh`；若出現 unrelated repository blocker，停止擴大修改並在報告中分開列出
- [ ] T043 執行 `git status --short`、`git diff --stat`、`git diff --name-only` 與完整 diff review，移除任何不屬於本功能的 formatting-only 或 incidental changes
- [ ] T044 產出 implementation report，包含 changed files、contract、角色驗證、tenant isolation、local、ngrok、GCP、targeted tests、full gate、warnings、remaining failures 與 commit readiness

## 任務依賴

```text
Phase 1：T001 → T004
             ↓
Phase 2：T005–T008（先確認紅燈）
             ↓
US1：T009 → T010 → T011 → T012
                  └──────→ T013 → T014 → T015 → T016
        T017 → T018
        上述完成 → T019
             ↓
US2：T020 → T021 → T022 → T023／T024
        T025–T027 → T028
             ↓
US3：T029 → T030 → T031 → T032 → T033 → T034 → T035 → T036
             ↓
Final：T037／T038 → T039 → T040 → T041 → T042 → T043 → T044
```

## 可平行工作

- T005、T006、T007、T008 可在不同測試檔案中平行撰寫。
- T017 可與 T009–T011 平行進行，但 T018 必須等 T017 完成。
- T025、T026、T027 可在 `AnimalPhoto` 公開介面固定後平行進行。
- T037 與 T038 可在 backend／frontend 實作都穩定後平行執行。

任何標示 `[P]` 的工作開始前，都要先確認不會同時修改同一檔案。

## 每階段停止條件

- **Phase 1**：目標環境存在 `current_photo_key` 與可信任 `MediaAsset` 不一致時，停止並提出資料修復計畫。
- **Phase 2**：測試在舊實作下沒有紅燈時，先修正測試，不進入 implementation。
- **US1**：任一跨 tenant 案例得到非 `404`，不得進入 frontend。
- **US2**：圖片請求未使用 `authFetch`、object URL 未撤銷或 context switch 可能保留舊圖，禁止進入部署驗證。
- **US3**：Network 仍出現私人 MinIO URL，禁止宣告完成。
- **Final**：unrelated quality-gate failure 不得以擴 scope、skip、disable 或放寬 gate 處理；停止並如實報告。

## 驗收標準

- [ ] 管理動物清單與詳細 API 不再回傳 MinIO signed URL
- [ ] STAFF、SHELTER_ADMIN、PLATFORM_ADMIN 可讀取目前 shelter 的圖片
- [ ] VOLUNTEER 無權讀取管理圖片
- [ ] A shelter 無法讀取 B shelter 的動物圖片
- [ ] 圖片必須具有可信任 media metadata
- [ ] 清單與詳細頁均透過 authenticated Blob 顯示
- [ ] context switch 不會殘留前一個 shelter 的圖片
- [ ] 本機與 ngrok 實際顯示成功
- [ ] GCP 不需要公開 MinIO 或新增 firewall rule
- [ ] 沒有 migration、Docker、Terraform、Nginx 或 unrelated feature 變更
- [ ] targeted validation 全部通過
- [ ] `git diff --check` 通過
- [ ] 完整 `verify_local` 結果已獨立報告

## 建議 Implementation Report 格式

```text
Management animal image proxy implementation completed: YES / NO
Local demo readiness: PASS / BLOCKED
ngrok demo readiness: PASS / BLOCKED
GCP deployment path readiness: PASS / BLOCKED / NOT RUN
Tenant isolation: PASS / FAIL
Targeted validation: PASS / FAIL
Full repository quality gate: PASS / BLOCKED

Changed files:
- ...

Evidence:
- API contract:
- STAFF / SHELTER_ADMIN / PLATFORM_ADMIN:
- Cross-tenant 404:
- Local image:
- ngrok image:
- Private MinIO URL absent:
- Frontend Blob cleanup:

Remaining warnings or failures:
- ...

Final commit SHA:
- ...
```

## Management Animal Image Proxy — Revised Implementation Plan

### Current Architecture Findings

- `ManagementAnimalService._read_payload()` 直接建立 `MediaAccessService(MinioStorageAdapter())` 並產生 signed URL；這是私人 MinIO origin 洩漏到 browser 的來源。
- `management_animals.py` 的所有管理端點已統一使用 `current_request_context`、`request_session` 與 `require_staff_or_admin`，新圖片端點應沿用，不建立 image-specific role system。
- `require_staff_or_admin()` 已要求 active organization context，並允許 STAFF、SHELTER_ADMIN、PLATFORM_ADMIN。
- `ManagementAnimalService` 現有 read/write query 直接使用 SQLAlchemy 並同時限制 `Animal.organization_id`；本修復留在相同 service，避免為單一讀取建立平行 repository architecture。
- `MediaAsset` 已提供 `organization_id`、`object_key`、`content_type`、`status` 與 `exif_removed` 所需 trust metadata。
- `MinioStorageAdapter.get(scope, key)` 已是現成 private storage read abstraction。
- `authFetch()` 會加入 Bearer token，並使用 `OrganizationRequestScope` 合併 caller 與 shelter lifecycle AbortSignal；其包裝後的 `blob()` 會在 body publish 前後再次檢查 request scope。
- `DiaryPhoto` 已提供可重用的 component-local AbortController 與 Blob URL cleanup 實作模式，但 AnimalPhoto 保持 feature scoped，不耦合 Growth Diary 樣式。
- 公開領養圖片 endpoint 已示範 tenant-scoped MediaAsset lookup 與 private MinIO proxy；管理端改用既有登入授權，不使用公開 token。

### Confirmed Root Cause

管理動物 JSON 中的 `photo_url` 是由 API 依 `MINIO_ENDPOINT=http://127.0.0.1:9000` 產生。ngrok 只公開 Web origin；外部 browser 解析 `127.0.0.1` 時指向使用者自己的裝置，因此圖片無法載入。圖片物件與 metadata 本身存在，問題位於 delivery boundary，不是資料遺失。

### Plan Adjustments

- **KEEP T005–T008**：維持 test-first，先證明舊實作失敗。
- **MODIFY T009–T011**：不新增 `AnimalRepository` method；沿用 `ManagementAnimalService` 的 tenant-scoped query convention。
- **KEEP T012–T015**：相對 endpoint、private MinIO read 與安全 response headers 方向相容。
- **MODIFY T016**：除了安全 `404`，必須加入 server-side exception logging，不能 silent swallow。
- **KEEP T017–T019**：canonical OpenAPI、runtime contract 與 generated TypeScript 必須同步。
- **KEEP T020–T021**：AnimalPhoto 負責 authenticated Blob 與 object URL lifecycle。
- **MODIFY T022**：reuse `authFetch`／`OrganizationRequestScope`，不建立第二套 organization-switch lifecycle。
- **KEEP T023–T044**：consumer、真實路徑、quality gate 與 report 順序維持。
- **REMOVE**：原先預期修改 `animal_repository.py` 的必要性。
- **ADD**：明確禁止以 `MediaAsset.purpose` 或 `subject` 當 trust gate，並增加 storage exception logging 驗證。

### Implementation Gate Result

- 本機 metadata inventory：126／126 筆 current photo 有可信任 MediaAsset，無資料 blocker。
- 現有 authorization、tenant context、storage read 與 frontend stale-request lifecycle 均可直接 reuse。
- 修復可限制在 management animal backend、frontend consumer、contract 與 focused tests。
- Gate：**可進入 Red tests 與 implementation**。
