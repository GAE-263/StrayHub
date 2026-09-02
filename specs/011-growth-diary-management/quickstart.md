# Quickstart：毛孩日記管理頁驗證

## Prerequisites

- Python 3.12、`uv`、Node.js、npm、Docker Compose
- 本機 PostgreSQL 與 MinIO
- 已套用本 feature migration
- 兩個收容所，以及 text-only、photo-only、AI succeeded／failed／unconfigured／legacy 日記 fixture
- JPEG、PNG、WebP、animated WebP、EXIF orientation、transparent PNG、超過 10 MB、超過 25M pixels 與難壓縮圖片 fixture

## 1. Local dependencies and migration

```bash
docker compose -f infra/local/docker-compose.yml up -d postgres minio
UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head
```

確認舊日記沒有被假造 AI provenance。

## 2. Backend validation

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check services/api/app/api/growth_diary.py services/api/app/application/growth_diary_service.py services/api/app/application/media_sanitization.py services/api/app/application/media_service.py services/api/app/api/line_webhook.py services/api/app/persistence/models/growth_diary.py services/api/app/persistence/repositories/growth_diary_repository.py
UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check services/api/app/api/growth_diary.py services/api/app/application/growth_diary_service.py services/api/app/application/media_sanitization.py services/api/app/application/media_service.py services/api/app/api/line_webhook.py services/api/app/persistence/models/growth_diary.py services/api/app/persistence/repositories/growth_diary_repository.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_media_sanitization.py tests/contract/test_growth_diary_management_contract.py tests/integration/test_growth_diary_management.py tests/integration/test_growth_diary_media_consistency.py tests/security/test_growth_diary_management_isolation.py
```

Expected：角色與 active shelter 驗證正確；A 查不到 B 的 entry/detail/photo；跨 tenant 與不存在 photo 使用安全 404；query/mood 在 count/page 前生效；新圖片只保存 final WebP；sanitization/storage/DB failure 不產生不完整日記或 silent orphan。

### Media policy assertions

- compressed input 超過 10 MB：完整拒絕。
- `Image.open()` 取得尺寸後、`source.load()` 前拒絕超過 25,000,000 pixels；Pillow decompression warning/error 同樣 fail closed。
- JPEG、PNG、WebP 都正規化為 `image/webp`；animated input 只有第一 frame。
- EXIF orientation 套用正確，final bytes 無 EXIF；transparent PNG 的 alpha 保留。
- 小圖不 upscale；正常輸出 long edge `<= 1600`、quality 82。
- 超過 2 MB 時依序驗證 quality 72、1280px/quality 68 fallback；最終仍超過 2 MB 則拒絕。
- final metadata 的 checksum、size、MIME 來自 final WebP，且 storage 不含 original/intermediate。

### Failure and compensation assertions

- sanitization failure：沒有 object、沒有 GrowthDiaryEntry。
- storage put failure：沒有 GrowthDiaryEntry。
- storage success + DB insert/flush/commit failure：DB rollback，已建立 object 由 per-event compensation 刪除。
- DB commit failure：不得送出 Growth Diary「已記錄」成功回覆，也不得註冊該 entry 的 AI task；LINE redelivery 使用 deterministic key 不產生多份 object。
- compensation delete failure：可觀測到 `growth_diary_orphan_cleanup_failed` exception log，root DB error 保留，response/log 不洩漏 object key 給使用者。
- commit 成功後 LINE reply／AI task registration 失敗：entry/object 保留，不執行 compensation，外部 side-effect failure 可觀測。

## 3. Contract generation

```bash
npm --prefix packages/contracts run generate
npm --prefix packages/contracts run check
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/contract/test_growth_diary_management_contract.py tests/contract/test_generated_contract_types.py
```

Expected：011 feature contract 已合併至 `specs/001-volunteer-care-report/contracts/openapi.yaml` 唯一 canonical；FastAPI runtime schema 與 generated TypeScript 一致。list schema 不含 `ai_raw_output`，detail 才包含完整 provenance/raw output；photo 只宣告 `image/webp`、`private, no-store`、`nosniff`。

## 4. Frontend validation

```bash
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
npm --prefix apps/web run format:check
npm --prefix apps/web run test:e2e -- e2e/growth-diary-management.spec.ts
```

Expected：desktop/mobile 導覽可進入；STAFF、SHELTER_ADMIN、active-context PLATFORM_ADMIN 可查看；原始內容與 AI 區塊分離；AI 顯示未確認與非診斷提示；raw output 只在 detail；圖片使用 authenticated Blob 且失敗只替換圖片；搜尋、mood、pagination、清除、retry 與 provenance disclosure 可用。

## 5. Responsive、a11y and tenant switch

```bash
npm --prefix apps/web run test:e2e -- e2e/p0-responsive.spec.ts e2e/p0-keyboard.spec.ts e2e/p0-a11y.spec.ts
```

在 360×800、768×1024、1024×768、1440×900 確認無水平 overflow、長文字可換行、圖片有 alt/fallback；切換 A → B 時 A 的延遲 JSON/detail/photo Blob 不出現在 B，object URL 已 revoke。

## 6. Manual acceptance

1. 以 A shelter STAFF 進入「毛孩日記」，確認 newest-first 與動物識別。
2. 篩選「需要關注」，確認只有 AI 建議人工查看且沒有診斷字樣。
3. 搜尋動物並切頁，確認 total 一致。
4. 分別以 STAFF、SHELTER_ADMIN、active-context PLATFORM_ADMIN 展開 AI 來源；新紀錄有 model/prompt/schema/time/raw output，legacy 顯示來源未留存，且 list response 沒有 raw output。
5. 以 VOLUNTEER、無 active shelter context 與 shelter B 使用者直接請求 A 的 detail/photo，確認拒絕且不存在／跨 tenant 行為一致。
6. 取得 photo，確認 `Content-Type: image/webp`、`Cache-Control: private, no-store`、`X-Content-Type-Options: nosniff`，且 URL 不含 object key/Bearer token/MinIO hostname。
7. 模擬 photo 404，確認 note 與 AI summary 仍在。
8. 切到 B shelter，確認 A 的文字、數量、名稱與照片不殘留，舊 object URL 已 revoke。
9. 確認第一版沒有 diary list/detail/photo/raw-output read audit event；既有 authentication、authorization、mutation audit 不受影響。
