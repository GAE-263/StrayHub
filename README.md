# 浪浪森友會

志工日常照護回報與動物近期歷程的本機優先 MVP。正式資料由 FastAPI／PostgreSQL CRM 保存；Next.js 是管理與 LIFF 介面，LINE Bot 與 Worker 透過既定 Application 邊界操作資料。

## 本機需求

- Docker Desktop／Docker Compose
- Python 3.11+（由 `uv` 管理執行環境）
- `uv`
- Node.js 與 npm
- 本機可用的 `openssl`（首次展示且 JWT 金鑰尚未設定時使用）

PostgreSQL 固定使用 `127.0.0.1:65432`，MinIO API 使用 `9000`，MinIO Console 使用 `9001`。這些值與 [`.env.example`](.env.example) 保持一致。

## 快速啟動

```bash
cp .env.example .env
docker compose -f infra/local/docker-compose.yml up -d postgres minio
uv run alembic upgrade head
uv run python -m scripts.seed_local
# 載入 T255 工作人員驗收用的固定 14 日 Timeline（需先完成 seed_local）
uv run python -m scripts.seed_t255_timeline
```

若 `.env` 的 `AUTH_JWT_ACTIVE_PRIVATE_KEY` 與 `AUTH_JWT_ACTIVE_PUBLIC_KEY` 為空，請先產生本機限定金鑰並填入 `.env`；不可將這些金鑰用於正式環境：

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out /tmp/strayhub-private.pem
openssl pkey -in /tmp/strayhub-private.pem -pubout -out /tmp/strayhub-public.pem
```

把兩個檔案內容分別填入 `AUTH_JWT_ACTIVE_PRIVATE_KEY` 與 `AUTH_JWT_ACTIVE_PUBLIC_KEY`。Shell 直接展示可使用 `./scripts/demo.sh`，它會在環境變數未提供時使用短期 process-local 金鑰。

## 啟動服務

分別開啟三個終端機：

```bash
# FastAPI
uv run python -m uvicorn services.api.app.main:app --reload --host 127.0.0.1 --port 8001

# Next.js
npm --prefix apps/web run dev -- --hostname 127.0.0.1 --port 3001

# Worker
uv run python -m services.worker.worker
```

- API health check：<http://127.0.0.1:8001/healthz>
- 管理前端：<http://127.0.0.1:3001>
- 管理登入頁：<http://127.0.0.1:3001/login>
- Swagger：<http://127.0.0.1:8001/docs>
- 本機資料帳號：`local-staff-a`、`local-volunteer-a`、`local-platform-admin`，密碼都是 `local-only-password`
- 另一個租戶帳號：`local-staff-b`、`local-volunteer-b`

`local-platform-admin` 是沒有 Shelter Membership 的平台級 `PLATFORM_ADMIN`，登入後可選擇並管理 `ORG-A`／`ORG-B`。

Seed 只建立虛構的 `ORG-A`／`ORG-B`，兩邊可以使用相同 Shelter Number，供租戶隔離展示。完成測試後可安全移除這組資料：

```bash
uv run python -m scripts.reset_local --yes
```

登入管理前端後，Next.js 會將 `/v1/*` 轉發至 `127.0.0.1:8001/v1/*`，再依登入帳號的 Membership 或平台管理員授權設定 Active Shelter Context；管理首頁會自動導向第一隻動物的 Timeline。預設展示帳號是 `local-staff-a`／`local-only-password`。

## LIFF HTTPS tunnel 與手機驗收

正式 LIFF／手機測試不可使用 `localhost`、fake LIFF ID 或單一 tunnel 同時承載 Web 與 API。完整流程與遮罩後證據格式見 [`specs/004-volunteer-entry-route-isolation/validation/controlled-line-evidence.md`](specs/004-volunteer-entry-route-isolation/validation/controlled-line-evidence.md)。

1. 先在本機啟動 FastAPI `127.0.0.1:8001` 與 Next.js `127.0.0.1:3001`。
2. 建立兩條獨立的HTTPS tunnel：Web→`3001`、API→`8001`。可使用：

   ```bash
   cloudflared tunnel --url http://127.0.0.1:3001
   cloudflared tunnel --url http://127.0.0.1:8001
   ```

   或在受控環境使用兩個獨立的`ngrok http 3001`／`ngrok http 8001` process。

3. 將API tunnel origin設定為Next.js server runtime的`API_BASE_URL`，將LIFF Console取得的LIFF ID設定為`LIFF_ID`，再重新啟動Next.js；兩者不是`NEXT_PUBLIC_*` client fallback。
4. 在同一LINE Login channel的LIFF Console設定HTTPS Web tunnel `/volunteer-entry` Endpoint並啟用`openid` scope。Rich Menu則使用`https://liff.line.me/<LIFF_ID>/volunteer-entry?entry=<opaque-reference>`，由`sync_line_rich_menu.py` dry-run驗證。
5. 使用受控LINE帳號執行controlled evidence中的Case A–D；raw ID token、raw entry reference、LINE user ID、Secret與protected data不得寫入Git、issue、terminal transcript或截圖。

## 一鍵本機展示

```bash
# 執行 Migration、Seed、US0～US3 與 AI 失敗降級 smoke，完成後啟動三個本機服務
./scripts/demo.sh

# 只執行展示前驗證，不啟動長駐服務
./scripts/demo.sh check
```

### 一鍵 LINE／LIFF 手機 Demo

`scripts/demo-line.sh` 會依序啟動 FastAPI、Next.js、Web tunnel，
並輸出 LIFF Endpoint 與手機入口。請先在 `.env` 填入真實受控測試值：

```dotenv
NGROK_URL=https://your-reserved-domain.ngrok.app
LIFF_ID=<LINE_LOGIN_CHANNEL_LIFF_ID>
LINE_LOGIN_CHANNEL_ID=<LINE_LOGIN_CHANNEL_ID>
SHELTER_ENTRY_REFERENCE=<SHELTER_ENTRY_REFERENCE>
START_WORKER=1
```

再執行：

```bash
./scripts/demo-line.sh
```

腳本使用 ngrok 的保留網址；先在 ngrok 建立或保留固定 HTTPS 網址，並完成本機
authtoken 設定，再將該網址設為 `NGROK_URL`。腳本只會公開 Web tunnel；Next.js 的
`/v1` server-side proxy 會使用本機 FastAPI 作為 `API_BASE_URL`，因此 API 不會直接公開到
Internet。腳本會以 `ngrok http --url "$NGROK_URL"` 啟動，若實際 tunnel URL 不符合設定就會失敗，
避免輸出會在重啟後變動的 LIFF Endpoint。腳本不會替你修改 LINE Developers Console；請將輸出的
`LIFF Endpoint` 填入 LIFF App 的 Endpoint URL，並從輸出的手機 LINE 入口開啟。
按 `Ctrl-C` 會停止本腳本啟動的程序。

目前單一收容所 Demo 會把 `entry` query 放在 `LIFF Endpoint`，手機入口只使用
`https://liff.line.me/<LIFF_ID>`。不要再把 `/volunteer-entry?entry=...` 加到手機
入口，否則 LINE 會將它與 Endpoint path 串接成重複路徑。

展示流程會驗證收容所／帳號隔離、動物／QR 選擇、LINE Bot Draft／Report、Timeline 與 AI 服務中斷時人工回報仍可保存。`DEMO_SKIP_DOCKER=1` 可在服務已由其他 Compose project 啟動時略過 `docker compose up`。

## 品質命令

Python：

```bash
uv run pytest -q
uv run pytest tests/test_feature_quality.py -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

目前 `mypy` 先固定檢查 domain、observability 與 database setup 的 typed boundary；既有 application／repository SQLAlchemy 型別會依序收斂，不以關閉檢查換取通過。

Frontend：

```bash
npm --prefix apps/web run quality
npm --prefix apps/web run test:mobile
npm --prefix apps/web run test:a11y
npm --prefix apps/web run build
```

前端 UX foundation：

```bash
npm --prefix apps/web run test:e2e:tooling
npm --prefix apps/web run test:e2e:p0:list
npm --prefix apps/web run test:e2e:p0
npm --prefix apps/web run test:visual
npm --prefix apps/web run test:a11y:browser
npm --prefix apps/web run test:axe
```

`apps/web/components/ui/` 是按需求維護的 shadcn/ui foundation；業務組合元件放在
`components/management/` 與 `features/`。新增操作圖示使用 `lucide-react` 的 named
import，icon-only 控制必須提供可理解的 accessible name。Tailwind token 集中在
`apps/web/app/globals.css`，P0 responsive viewport 為 360、768、1024 與 1440px。
UI migration 只改 presentation 與可觀察互動，不得改動既有 API 契約、CRM 唯一事實來源、
原始回報保存、AI 人工覆核邊界或 Organization／Active Shelter Context 隔離。

P0 visual baseline 位於 `apps/web/e2e/p0-visual.spec.ts-snapshots/`；只有 reviewer 確認
設計變更後才能執行 `test:visual:update`。P1 browser scripts 是獨立證據，不是 P0 gate 依賴。

Contract Types：

```bash
npm --prefix packages/contracts run check
```

完整本機 Gate：

```bash
./scripts/verify_local.sh
```

Gate 會執行 Migration、空資料庫 Bootstrap、完整 Python／Frontend 測試、Ruff、TypeScript、Next build、OpenAPI generated types、MinIO／GCS adapter contract 與 Secret scan。沒有 Dockerfile 時，Docker build 會明確顯示為 skipped；這不代表 GCP 已部署。

## API／Contract／LINE 邊界

- HTTP 唯一契約：[OpenAPI](specs/001-volunteer-care-report/contracts/openapi.yaml)；TypeScript 型別由 `openapi-typescript` 產生，不能手動修改。
- OpenAPI 產生型別位於 [`packages/contracts/src/openapi.ts`](packages/contracts/src/openapi.ts)。
- LINE Webhook 必須先驗證原始 Body 與 `X-Line-Signature`，再依 `webhookEventId` 冪等處理。
- 本機 LINE 流程使用 Mock Adapter／虛構事件，不呼叫正式 LINE API。
- PostgreSQL transaction 必須設定已驗證的 Organization Scope；前端傳入的 Organization、Animal、Draft、QR 或 Object Key 不能取代後端授權。
- MinIO 是本機 Object Storage；GCS 只在 GCP Demo Gate 後驗證，不能把本機通過結果當成 GCP 部署證據。

## GCP Demo 邊界

GCP Demo 必須在本機品質 Gate 與 Terraform／GCS／IAM Gate 通過後才可進行。Terraform 唯一來源是 `infra/gcp-demo/terraform/`；本機開發不需要 GCP credentials，也不會由 `scripts/demo.sh` 建立雲端資源。

## 相關文件

- [Feature Specification](specs/001-volunteer-care-report/spec.md)
- [Implementation Plan](specs/001-volunteer-care-report/plan.md)
- [Task List](specs/001-volunteer-care-report/tasks.md)
- [Quickstart](specs/001-volunteer-care-report/quickstart.md)
- [Contract Index](specs/001-volunteer-care-report/contracts/README.md)
