# Quickstart：毛孩日記管理頁驗證

## Prerequisites

- Python 3.12、`uv`、Node.js、npm、Docker Compose
- 本機 PostgreSQL 與 MinIO
- 已套用本 feature migration
- 兩個收容所，以及 text-only、photo-only、AI succeeded／failed／unconfigured 日記 fixture

## 1. Local dependencies and migration

```bash
docker compose -f infra/local/docker-compose.yml up -d postgres minio
UV_CACHE_DIR=/tmp/uv-cache uv run alembic upgrade head
```

確認舊日記沒有被假造 AI provenance。

## 2. Backend validation

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check services/api/app/api/growth_diary.py services/api/app/application/growth_diary_service.py services/api/app/persistence/models/growth_diary.py
UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check services/api/app/api/growth_diary.py services/api/app/application/growth_diary_service.py services/api/app/persistence/models/growth_diary.py
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/contract/test_growth_diary_management_contract.py tests/integration/test_growth_diary_management.py tests/security/test_growth_diary_management_isolation.py
```

Expected：角色與 active shelter 驗證正確；A 查不到 B 的 entry/detail/photo；跨 tenant 與不存在 photo 使用安全 404；query/mood 在 count/page 前生效；storage failure 不影響文字及摘要。

## 3. Contract generation

```bash
npm --prefix packages/contracts run generate
npm --prefix packages/contracts run check
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/contract/test_growth_diary_management_contract.py tests/contract/test_generated_contract_types.py
```

Expected：canonical OpenAPI、FastAPI runtime schema 與 generated TypeScript 一致。

## 4. Frontend validation

```bash
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
npm --prefix apps/web run format:check
npm --prefix apps/web run test:e2e -- e2e/growth-diary-management.spec.ts
```

Expected：desktop/mobile 導覽可進入；原始內容與 AI 區塊分離；AI 顯示未確認與非診斷提示；圖片使用 authenticated Blob 且失敗只替換圖片；搜尋、mood、pagination、清除、retry 與 provenance disclosure 可用。

## 5. Responsive、a11y and tenant switch

```bash
npm --prefix apps/web run test:e2e -- e2e/p0-responsive.spec.ts e2e/p0-keyboard.spec.ts e2e/p0-a11y.spec.ts
```

在 360×800、768×1024、1024×768、1440×900 確認無水平 overflow、長文字可換行、圖片有 alt/fallback；切換 A → B 時 A 的延遲 JSON/detail/photo Blob 不出現在 B，object URL 已 revoke。

## 6. Manual acceptance

1. 以 A shelter STAFF 進入「毛孩日記」，確認 newest-first 與動物識別。
2. 篩選「需要關注」，確認只有 AI 建議人工查看且沒有診斷字樣。
3. 搜尋動物並切頁，確認 total 一致。
4. 展開 AI 來源；新紀錄有 model/prompt/time/raw output，legacy 顯示來源未留存。
5. 模擬 photo 404，確認 note 與 AI summary 仍在。
6. 切到 B shelter，確認 A 的文字、數量、名稱與照片不殘留。
