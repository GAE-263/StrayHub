# GCP Deployment Gate Evidence

狀態：T238 PASS（2026-08-09）。T238 只證明部署前 Gate 通過；本次沒有執行 Terraform `apply`、
Cloud Run YAML 部署或建立任何 GCP 資源。

## Gate 命令

```bash
bash infra/gcp-demo/deploy-gate.sh
```

Gate 必須在本機 PostgreSQL `127.0.0.1:65432`、Node／npm、`uv`、Terraform CLI 與 Docker
daemon 可用時執行。Gate 會停止於任一失敗，不接受 `skip` 或自動降級。

## 證據紀錄

| 項目 | 結果 | 證據 |
|---|---|---|
| Python Ruff／Pytest | PASS | `uv run ruff check .`、`ruff format --check .`、248 tests |
| Frontend quality／build | PASS | 22 Vitest、TypeScript、Mobile／A11y、Prettier、Next build |
| OpenAPI Contract Types | PASS | `npm --prefix packages/contracts run check` |
| Empty Migration／Seed | PASS | Full local regression included T224 boundaries |
| Organization A／B isolation | PASS | Full local regression and isolation contract |
| MinIO／GCS Adapter Contract | PASS | 12 migration／isolation／adapter tests |
| LINE Adapter Contract | PASS | Mock／formal adapter contract included |
| Secret scan | PASS | No credential-shaped material in `infra/gcp-demo` |
| Terraform fmt／init／validate | PASS | Terraform 1.15.8、Google provider 6.50.0、backend disabled |
| API／Worker／Web Docker build | PASS | `strayhub-demo-api:gate`、`worker:gate`、`web:gate` |

Gate 完成摘要：`Deployment Gate passed. No Terraform apply was executed.`

工具與環境：本機 PostgreSQL `127.0.0.1:65432`；Terraform `v1.15.8`；Google provider `v6.50.0`；
Docker Desktop `desktop-linux` builder。Docker web build 的 `npm ci` 輸出既有 dependency audit
warning，但 build、既定 Secret scan 與 Gate command 均成功；此 warning 不被誤記為正式安全審查。

## Demo 資料與安全邊界

- 僅使用 `ORG-A`／`ORG-B` 與虛構帳號／動物；不同租戶可使用相同 Shelter Number。
- Terraform 僅引用 Secret Manager Secret name，不含 Secret 明文。
- CI 只執行 format／validate／test／build；Workflow 明確不執行 Terraform `plan` 或 `apply`。
- 真實 Cloud SQL、GCS IAM／Signed URL、正式 LINE HTTPS／Rich Menu 與 Cloud Logging 需要
  T239～T244 部署後驗證，不能以本 Gate 取代。
