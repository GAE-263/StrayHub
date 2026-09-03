# 浪浪森友會

志工日常照護回報與動物近期歷程的本機優先 MVP。正式資料由 FastAPI／PostgreSQL CRM 保存；Next.js 是管理與 LIFF 介面，LINE Bot 與 Worker 透過既定 Application 邊界操作資料。

## 本機需求

- Docker Desktop／Docker Compose
- Python 3.12（由 `uv` 管理執行環境）
- `uv`
- Node.js 與 npm
- 本機可用的 `openssl`（首次展示且 JWT 金鑰尚未設定時使用）

PostgreSQL 固定使用 `127.0.0.1:65432`，MinIO API 使用 `9000`，MinIO Console 使用 `9001`。這些值與 [`.env.example`](.env.example) 保持一致。

## 快速啟動：Normal Demo

```bash
cp .env.example .env
uv sync --dev
npm ci --prefix apps/web
./scripts/demo.sh
# 僅 bootstrap／驗證，不啟動服務：
./scripts/demo.sh check
# 強制同步最新官方 MOA 資料，驗證後啟動服務：
./scripts/demo.sh refresh
```

正常 demo 只建立毛小孩幸福聯盟協會（5 隻）、新北市新店區公立動物之家
（犬，最多 60 隻）、新北市五股區公立動物之家（犬，最多 60 隻）。
流程包含 Docker、Alembic、runtime-role 最小 grants、FurKids、MOA 資料確認、
共用觀察詞彙、demo 帳號與照片／QR 驗證；不執行測試 fixture seed。

- 管理介面：[本機 Web](http://127.0.0.1:3001/login)
- API：[healthz](http://127.0.0.1:8001/healthz)、[Swagger](http://127.0.0.1:8001/docs)
- 三收容所管理員：`demo-furkids-admin`（三個明確 SHELTER_ADMIN memberships）。
- 平台治理：`demo-platform-admin`（無 Shelter Membership）。
- 單一收容所志工：`demo-furkids-volunteer`、`demo-xindian-volunteer`、
  `demo-wugu-volunteer`；各自只有所屬收容所 membership/grant。
- 上述帳號密碼皆為 `local-only-password`；僅供本機，無真實個資。

已知既有限制：純平台帳號在 `strayhub_runtime` 連線下的登入組織清單為空，
尚待獨立授權修正；三收容所展示請使用 membership-based `demo-furkids-admin`。
詳細驗證與既有 DB 的未知 fixture 保留情況見下方資料流程文件。

正常 `demo.sh`／`demo.sh check` 先完整驗證 PostgreSQL 與 MinIO 中的 MOA
動物、來源、QR、MediaAsset、物件存在性與照片 checksum；資料有效就直接沿用，
不呼叫 MOA API，也不執行名稱 enrichment。資料缺少或照片損壞時才會自動 live sync
並再次驗證，因此 fresh DB／fresh MinIO 不需要額外手動步驟。

正常啟動保證的是有效的本機三收容所 snapshot，不保證最新官方資料；需要 freshness 時
使用 `./scripts/demo.sh refresh`。refresh 仍沿用 importer 的未變更照片重用規則，但會執行
MOA metadata 與官方名稱同步；若同步失敗，即使既有資料仍可驗證，也會明確回報並以非零
結束。即時來源可能少於 60 或已有較多歷史匯入，驗證命令回報實際數量，不自行刪除動物。

Compose 的 `minio-data` volume 會跨一般 demo 重啟與 `docker compose down` 保留，這是後續
啟動能重用照片的前提。執行 `docker compose down -v` 會刪除 cached media，下一次 bootstrap
會因照片驗證失敗而重新下載／修復。

JWT 未提供時，demo.sh 使用短期 process-local 金鑰；手動啟動請設定
`AUTH_JWT_ACTIVE_PRIVATE_KEY`／`AUTH_JWT_ACTIVE_PUBLIC_KEY`，不可用於正式環境。

## 非本機設定安全檢查

`APP_ENV=local` 保留 `.env.example` 的 loopback、fake LINE、local MinIO 與 demo 金鑰
便利設定；明確的 `test`／`testing` 也允許測試自行注入的 deterministic 值。其他所有環境
會在 API 接受流量前集中檢查設定，Worker 與 Alembic 則在連線資料庫前檢查其必要的
`DATABASE_URL`。錯誤會一次列出欄位名稱與原因，不會輸出 secret 內容。

API 的非本機必要設定包括遠端 PostgreSQL、目前實際使用的 MinIO backend、JWT active
signing/verification keys 與安全 key references、animal confirmation secret，以及支援的非本機
PII provider（目前為 GCP KMS），以及既有 runtime 所需的 LINE channel、token 與 LIFF ID。
`AI_PROVIDER=mock` 不需要 API key；選擇其他 provider 時才需要安全的 `AI_ENDPOINT`、
`AI_API_KEY` 與 model name。GCS 欄位目前只供顯式注入的 GCS adapter 使用，尚不是 API
runtime storage selector，因此不會僅因欄位存在就被全域要求。

非本機會拒絕空值、已知 repository local/fake defaults、`fake-`／`local-only-` prefixes，
以及 `changeme`、`change-me`、`example`、`test-secret`、`dev-secret`、`dummy`、
`placeholder`、`minioadmin` 等明確 placeholder。資料庫、MinIO 與外部 AI endpoint 也不可使用
loopback host；private/internal hostname 仍可使用。典型失敗格式如下：

```text
Unsafe non-local configuration (production):
- AUTH_JWT_ACTIVE_PRIVATE_KEY is missing
- MINIO_ACCESS_KEY uses a placeholder
```

在建立或更新非本機部署前，請從部署平台的 secret/config 注入所有必要值；不要把真實值
加入 `.env.example` 或版本庫。

## Test Fixtures：與 Demo 分開的資料庫

ORG-A／ORG-B／ORG-DISABLED、`local-staff-a`、`local-volunteer-a` 等
皆為測試 fixtures，不是正常 demo。後端測試的標準單一入口會建立／重用
`strayhub_test`、執行 migration，然後將其餘參數傳給 pytest：

```bash
uv run python -m scripts.test_local
uv run python -m scripts.test_local tests/unit/test_demo_bootstrap.py -q
```

若要人工載入 fixture，必須明確使用專用測試 DB：

```bash
export DATABASE_URL=postgresql+asyncpg://strayhub:strayhub@127.0.0.1:65432/strayhub_test
export STRAYHUB_TEST_DATABASE_URL=postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub_test
uv run alembic upgrade head
uv run python -m scripts.configure_runtime_role --apply
uv run python -m scripts.seed_test_fixtures
# 可選的測試延伸：
uv run python -m scripts.seed_t255_timeline
```

`scripts.seed_local`、`scripts.seed_test_fixtures`、`scripts.seed_t255_timeline`
與 `scripts.seed_medical_care` 均為只能指向 loopback `strayhub_test` 的測試路徑；
安全檢查會在非 PostgreSQL、遠端 host 或其他 DB 名稱時 fail closed。
LINE、QR、E2E、auth、volunteer、isolation 與 AI 失敗降級測試請使用上述
專用 DB；不要讓完整測試污染 demo DB。

## 清理既有本機 Demo

先備份並停止寫入者；以下命令只處理已知虛構 fixtures，不清空資料庫：

```bash
uv run python -m scripts.cleanup_legacy_demo_fixtures       # 唯讀預覽
uv run python -m scripts.cleanup_legacy_demo_fixtures --yes # 確認後才刪除
uv run python -m scripts.verify_demo_data --photos
```

只允許 APP_ENV=local/test、loopback DB；拒絕 production/staging、遠端主機。
ORG-A/B/DISABLED 以外的未知組織會保留並阻擋 exact-demo 驗證，需另行人工確認。
保留三收容所、共用詞彙、平台設定與 MinIO 照片；不新增 migration、不改 RLS。
完整盤點、帳號、清理與離線沿用規則見 [Demo/Test 資料流程](docs/demo/data-workflows.md)。

## LIFF HTTPS tunnel 與手機驗收

正式 LIFF／手機測試不可使用 `localhost` 或 fake LIFF ID。本機實機流程使用 nginx
把 Web 與 API 收斂為一個 origin，再以一條 tunnel 公開；完整流程與遮罩後證據格式見
[`specs/004-volunteer-entry-route-isolation/validation/controlled-line-evidence.md`](specs/004-volunteer-entry-route-isolation/validation/controlled-line-evidence.md)。

志工申請使用一個 LINE Bot 與一個 LIFF App。LIFF Console 的唯一 Endpoint URL
設為 Web tunnel 的 `/volunteer-application`；Rich Menu 的「志工報名」直接開啟
canonical `https://liff.line.me/<LIFF_ID>`，地區與收容所由 LIFF 的動態公開目錄選擇。
外部 shelter-specific link 仍可用 `organization_id` 預選；它只是公開申請目標，後端
仍會檢查 active organization 與 enabled policy，只有管理員核准後建立的
membership/grant 才是授權。

實體 QR、海報、外部網站或收容所櫃台入口保留
`https://liff.line.me/<LIFF_ID>?entry=<opaque-reference>`，由相同 Endpoint 轉入既有
`shelter_entry_reference` 流程。正常 Bot 選擇不需要也不 seed entry reference。

1. 先在本機啟動 FastAPI `127.0.0.1:8001` 與 Next.js `127.0.0.1:3001`。
2. `test_line_local.sh` 按需啟動 host nginx `127.0.0.1:8082`：`/healthz`、`/v1/*`
   保留原 path 送 FastAPI，其餘（含 `/_next/*` 與 HMR WebSocket）送 Next.js。
3. 一條 ngrok tunnel 只公開 nginx `8082`。瀏覽器使用相對 `/v1`，nginx 直接送 API，
   不需要 wildcard CORS，也不會把 `/_next/webpack-hmr` 誤送 FastAPI。
4. 將輸出的 public origin 設為 Next.js server runtime `API_BASE_URL`，將 LIFF Console
   取得的 LIFF ID 設為 `LIFF_ID`，並把不含 scheme 的 public host 設為
   `LINE_DEMO_WEB_ORIGIN_HOST`；這些不是 `NEXT_PUBLIC_*` client fallback。
5. 在同一 LINE Login channel 的 LIFF Console 設定 public origin 的
   `/volunteer-application` Endpoint 並啟用 `openid` scope。Rich Menu 的實體入口使用
   `https://liff.line.me/<LIFF_ID>?entry=<opaque-reference>`，由
   `sync_line_rich_menu.py` dry-run 驗證。
6. 使用受控LINE帳號執行controlled evidence中的Case A–D；raw ID token、raw entry reference、LINE user ID、Secret與protected data不得寫入Git、issue、terminal transcript或截圖。

### 驗證既有本機 Stack 的 LINE Bot／LIFF 實機入口

先以 `./scripts/demo.sh` 啟動既有 API 與 Web，再執行：

```bash
./scripts/test_line_local.sh --print-env # 只印非機密解析結果
./scripts/test_line_local.sh --no-tunnel # 檢查 env、routes 與既有服務
./scripts/test_line_local.sh             # 啟動 nginx + 一條 ngrok tunnel
./scripts/test_line_local.sh stop        # 只停止本 helper 擁有的 nginx/ngrok
```

資料流共用一個 HTTPS origin：

```text
LINE Platform → ngrok → nginx → FastAPI /v1/line/webhook
Phone LINE → LIFF → ngrok → nginx → Next.js
Browser relative /v1 → nginx → FastAPI
```

nginx config 位於 `infra/local/nginx/line-local.conf.template`，只在實機測試時由 helper
render 到暫存目錄，不改變一般 `demo.sh`。ngrok URL 產生後，Next.js 必須以輸出的
`API_BASE_URL`、`LIFF_ID` 與不含 scheme 的 `LINE_DEMO_WEB_ORIGIN_HOST` 重新啟動；
修改目前 shell 或 `.env` 不會改變已啟動 process。helper 不會自動改 `.env`、LINE
Developers 設定或 Rich Menu，也不會停掉不屬於它的 nginx/ngrok。

這個 local topology 刻意模擬未來可能採用的 GCP nginx single-origin routing，但本項目
沒有實作、部署或變更任何 GCP 資源。

角色 Rich Menu 與新的公開志工／領養入口在 production 受
`LINE_ROLE_MENU_FEATURES_ENABLED=false` 保護。實機 smoke 尚未以精確 release commit
留下核准 evidence 前不得啟用；啟用時 preflight 會同時要求公開 HTTPS origin、default／
volunteer／staff menu IDs、staff LIFF ID 及 LINE credential。完整狀態與設定見
[LINE 角色選單](docs/line-role-menu-framework.md) 與
[LINE 帳號設定](docs/line-account-setup.md)。

## 一鍵本機展示

```bash
# 執行 Migration、runtime grants、三收容所資料與照片驗證，完成後啟動三個本機服務
./scripts/demo.sh

# 只執行展示前驗證，不啟動長駐服務
./scripts/demo.sh check

# 強制抓取最新官方 MOA 資料、完成驗證後啟動長駐服務
./scripts/demo.sh refresh
```

### 一鍵 LINE／LIFF 手機 Demo

`scripts/demo-line.sh` 是既有的保留網址 LIFF-only 流程，會依序啟動 FastAPI、Next.js、Web tunnel，
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
Internet；它不涵蓋 LINE Platform webhook。需要同時驗證 Bot webhook 與 LIFF 時，使用
上方 `test_line_local.sh` 的 nginx single-origin 流程。腳本會以
`ngrok http --url "$NGROK_URL"` 啟動，若實際 tunnel URL 不符合設定就會失敗，
避免輸出會在重啟後變動的 LIFF Endpoint。腳本不會替你修改 LINE Developers Console；請將輸出的
`LIFF Endpoint` 填入 LIFF App 的 Endpoint URL，並從輸出的手機 LINE 入口開啟。
按 `Ctrl-C` 會停止本腳本啟動的程序。

LIFF Endpoint 固定為 `/volunteer-application`，動態 target 放在 canonical LIFF
入口的 query：Bot 使用 `organization_id`，實體／外部入口使用 `entry`。不要把
Endpoint path 再附加到 `https://liff.line.me/<LIFF_ID>`，否則 LINE 會與 Console
Endpoint path 串接成重複路徑。

本機可使用既有 fake LINE verifier 安全模擬全新身分，不需 seed User、membership、
grant 或 application。先從 `GET /v1/public/volunteer-organizations` 取得 demo 組織 UUID，
再以不含真實個資的 token 與資料呼叫 status／submit：

```json
{
  "id_token": "local-id-token:demo-new-applicant-xindian",
  "organization_id": "<XINDIAN_ORGANIZATION_UUID>",
  "applicant_name": "本機測試志工",
  "phone_number": "0900000000",
  "client_request_id": "<NEW_UUID>",
  "consent_acknowledged": true,
  "service_dates": ["<TODAY_OR_NEXT_13_DAYS>"]
}
```

status 不建立身分；首次成功 submit 會依現有 service 建立 applicant `User` 與
`LineUserBinding`，申請保持 pending。未來若公開連結需要更強的來源綁定，可另加
短效 signed Bot application context（user + organization + purpose + expiry）；V1 不實作。

正常 demo 不建立 LINE fixture 或執行測試套件；完整隔離、LINE Bot、Timeline 與 AI 失敗降級驗證由獨立 test DB 執行。`DEMO_SKIP_DOCKER=1` 可在本機服務已啟動時略過 `docker compose up`。

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

## 部署邊界

正式部署的唯一應用執行環境是 GCE + Compose；共享 Secret Manager、KMS 與備份 GCS
由 `infra/gcp-platform/terraform/` 管理。不可執行的舊 GCP Demo／Cloud Run 設計已在 Phase F6
移除；歷史脈絡保存在 [legacy-gcp-demo.md](docs/deployment/history/legacy-gcp-demo.md)。本機開發不需要
GCP credentials，也不會由 `scripts/demo.sh` 建立雲端資源。

## 相關文件

- [Feature Specification](specs/001-volunteer-care-report/spec.md)
- [Implementation Plan](specs/001-volunteer-care-report/plan.md)
- [Task List](specs/001-volunteer-care-report/tasks.md)
- [Quickstart](specs/001-volunteer-care-report/quickstart.md)
- [Contract Index](specs/001-volunteer-care-report/contracts/README.md)

## LINE 角色選單與工作人員動物輸入

依角色（訪客/志工/領養人/工作人員）自動切換 LINE Rich Menu，以及工作人員透過 LINE/LIFF
新增動物與健康紀錄兩支端點，屬於本專案獨立的一批工作，尚未在上面的一鍵 demo 流程中串接。
細節與設定步驟見：

- [`docs/line-role-menu-framework.md`](docs/line-role-menu-framework.md) — 角色→選單框架、`scripts/sync_line_role_menus.py`
- [`docs/staff-animal-line-input.md`](docs/staff-animal-line-input.md) — `POST /v1/management/animals`、`POST /v1/management/animals/{animalId}/health-records`
- [`docs/line-account-setup.md`](docs/line-account-setup.md) — LINE Console 串帳號完整步驟
