# Implementation Plan: 敏感資料傳輸與紀錄防護

**Branch**: `012-sensitive-data-transport-hardening` | **Date**: 2026-09-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/012-sensitive-data-transport-hardening/spec.md`

## Summary

以「源頭不產生禁止 URL」為主控制，配合敏感參數分類／例外登錄、跨層 log 去敏、公開 demo 路由 allowlist 與 sentinel runtime 驗證，修正登入表單在 hydration 前退化為 GET 的密碼外洩，並把相同控制延伸至 LINE／LIFF、QR、圖片 capability、staff signed URL、redirect 與 CLI 輸出。既有 authentication、tenant isolation、RLS 與各 capability 的業務授權不變。

## Technical Context

**Language/Version**: Python 3.12；TypeScript 5.7；Bash

**Primary Dependencies**: FastAPI、Pydantic、SQLAlchemy、React 19、Next.js 15、nginx、ngrok、LINE LIFF SDK

**Storage**: PostgreSQL 與物件儲存沿用既有模型；本功能預期不新增持久化資料表

**Testing**: Pytest、Vitest、Playwright、既有 shell／nginx contract tests、`git diff --check`

**Target Platform**: macOS 本機 demo、Linux／GCP 部署、LINE／LIFF WebView 與一般瀏覽器

**Project Type**: FastAPI + Next.js Web application，含 nginx edge、LINE webhook／LIFF 與本機 demo tooling

**Performance Goals**: 安全檢查與 URL canonicalization 不增加可察覺的登入或 LIFF 操作延遲；access log 仍可支援 method、path、status、size、latency 與 correlation 診斷

**Constraints**: 禁止在 URL 出現 password／session credential；必要 URL capability 必須 fail closed、tenant-bound、可撤銷或短效且不留原值；不得破壞合法 query、LINE 簽章、LIFF callback 或圖片載入

**Scale/Scope**: 全 repository 的 Web 表單與 URL builder、FastAPI access/application logging、Next proxy、local／GCP nginx、ngrok demo scripts、LINE／LIFF／QR／media flow、測試與 runbook

## Constitution Check

_GATE: Phase 0 前與 Phase 1 後皆通過。_

- **I. CRM 唯一事實來源：PASS** — 不新增業務資料副本；例外清單是工程政策，不承載 CRM 狀態。
- **II–IV. 原始資料／AI：PASS** — 不變更回報或 AI 資料。
- **V. 志工低摩擦：PASS** — LIFF 必要 callback／entry flow 保留；安全清理不得增加志工輸入。
- **VI. 歷史可追溯：PASS** — 不修改照護歷史；安全事件只記錄不可逆、非秘密識別資訊。
- **VII. LINE 僅為輸入通道：PASS** — LINE webhook 簽章、後端授權與 idempotency 不降低。
- **VIII. 權限、隱私與稽核：PASS** — 本功能直接收斂 credential transport、log 與公開暴露面。
- **IX. P0 獨立：PASS** — 登入源頭修正、log 防護與預設 tunnel allowlist 可獨立驗收，不依賴 CDN 或 session redesign。
- **X. 文件與品質：PASS** — 文件以台灣正體中文為主；Python 變更在實作階段依 constitution 跑完整 Ruff／Pytest gate。
- **XI. 多收容所隔離：PASS** — 所有 shelter-owned capability 保留 organization 與資源綁定；禁止以 query 中的 organization 直接授權。

## Project Structure

### Documentation (this feature)

```text
specs/012-sensitive-data-transport-hardening/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   └── requirements.md
└── contracts/
    └── security-boundary.md
```

### Source Code (repository root)

```text
apps/web/
├── app/login/page.tsx
├── app/v1/[...path]/route.ts
├── app/(volunteer)/**
├── app/(volunteer-onboarding)/**
├── lib/**
└── e2e/**

services/api/app/
├── api/{authentication,line_webhook,media,qr_codes}.py
├── application/{animal_selection,media_access,qr_token_service}.py
├── observability/logging.py
└── main.py

infra/
├── local/nginx/line-local.conf.template
└── edge-nginx/strayhub.enadv.quest.conf

scripts/
├── demo.sh
├── demo-line.sh
├── test_line_local.sh
└── issue_volunteer_entry_reference.py

tests/
├── contract/
├── integration/
├── security/
└── isolation/
```

**Structure Decision**: 沿用既有 Web、API、observability、nginx 與 script 邊界；不建立新的 service layer 或資料表。安全分類與例外登錄放在可由測試讀取的單一政策文件／模組，實際 enforcement 留在各既有邊界。

## Delivery Strategy

完整現況證據、Sensitive URL Registry及每個可獨立驗收的Task ID見
[security-analysis.md](security-analysis.md)。以下保留phase層級摘要；`tasks.md`必須沿用該文件的
SEC-A01～SEC-C04切分，不得合併成單一「Fix security」工作。

### Phase A — 立即封堵登入 URL 外洩

1. 登入表單加入安全的原生提交語意，hydration 前不可退化成 credential GET。
2. 移除 password 預填；E2E 明確填入 synthetic credential。
3. 對 legacy `/login?...` 禁止採信 credential 並 canonicalize 至乾淨 URL。
4. 為 `/login` 建立 query-free、Referer-free access logging，並補 browser／proxy／log regression。
5. 將目前已出現在 ngrok URL 的 demo credential 視為曝光：停止 tunnel、輪替、清理可控 log 並留下 runbook evidence。

### Phase B — 全專案 URL 與 log policy 收斂

1. 建立敏感資料分類與 URL exception registry。
2. 逐項登錄／驗證 `entry`、`qr_token`、photo capability、standard callback 與 staff signed URL。
3. 統一 Uvicorn、application logger、nginx、Next 與 script 的遮罩規則；保留合法 query 的診斷價值。
4. 對讀取後不再需要的 query 執行一次性清理，並保留必要的 retry／recovery 資訊。
5. 對 CLI 必須輸出的 raw one-time reference 加上 terminal-only、禁止持久化與輪替提示。

### Phase C — 公開 demo 最小暴露與防回歸

1. local LINE tunnel 改為必要 route allowlist，預設拒絕 login／management。
2. 若保留遠端管理 demo，使用明確 opt-in、synthetic-only guard、短效 credential 與停止時撤銷流程。
3. 新增 static contract scan 與 sentinel runtime matrix，涵蓋正常、pre-hydration、callback、Referer、error、跨租戶與 replay。
4. 將 security boundary、incident response 與 reviewer checklist 納入 README／quickstart。

## Post-Design Constitution Re-check

Phase 1 設計沒有新增 constitution 例外。必要 URL token 被定義為受控 capability，而不是繞過 VIII／XI；公開 demo allowlist 強化最小權限；合法 query 保留，避免以全面移除 query 破壞既有功能。實作若需要改變 token lifetime、authentication contract、RLS、LINE webhook 簽章或 GCP topology，必須拆成獨立規格，不得在本功能順手變更。

## Complexity Tracking

無 constitution 違規，不需登錄例外。
