# GCP Demo 環境契約

## 建立前置條件

只有以下結果全部通過才可部署 Demo：

- `ruff check .`
- `ruff format --check .`
- `pytest`
- Frontend 測試
- `npm --prefix packages/contracts run check`
- 空資料庫完整 Database Migration
- 本機關鍵流程
- Organization／Shelter A、B 隔離
- MinIO Adapter 測試
- GCS Adapter Contract Test
- `terraform fmt -check -recursive infra/gcp-demo/terraform`
- `terraform -chdir=infra/gcp-demo/terraform validate`
- Demo 資料掃描確認不含真實個資或正式收容所敏感資料

## Demo 元件

GCP Demo 基礎設施由 `infra/gcp-demo/terraform/` 的 Terraform 設定管理；本機開發不依賴這些 GCP 資源。Cloud Run、Service Account、IAM 與服務環境設定同樣由 Terraform 管理，`cloud-run-*.yaml` 不得作為正式部署來源。

- Next.js Cloud Run Service
- FastAPI Cloud Run Service
- Background Worker／Job
- Cloud SQL for PostgreSQL
- Cloud Storage
- Secret Manager
- Artifact Registry
- Cloud Logging

FastAPI Cloud Run 在 Demo 環境啟用正式 `LineMessagingApiAdapter`；LINE channel secret 與 channel access token 由 Secret Manager 提供，不能寫入 image、Terraform state 的明文輸出、Rich Menu action 或 application log。Rich Menu 由版本化設定及 `scripts/sync_line_rich_menu.py` 發布，不視為 Terraform 管理的 GCP 資源。

Terraform 至少分為 `cloud-run.tf`、`cloud-sql.tf`、`storage.tf`、`iam.tf`、`observability.tf`、`variables.tf` 與 `outputs.tf`。CI 以 `infra/gcp-demo/terraform/**/*.tf` Path Filter 觸發；尚未加入 Terraform 設定時明確跳過，不阻擋本機 Setup。

## 部署後驗證

部署後必須重新驗證 Database Migration、Cloud Storage 權限、Signed URL、LIFF HTTPS、QR Code、Shelter A／B 隔離與 AI 失敗降級。Cloud SQL 連線、IAM、Service Account 與 Signed URL 行為不以本機通過作為證據。

## 資料限制

Demo 只使用虛構資料或合法公開資料；不可把本機 Seed Data 中的真實個資、正式收容所敏感資料或長效祕密帶入 Demo。
