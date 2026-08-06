# GCP Demo 環境契約

## 建立前置條件

只有以下結果全部通過才可部署 Demo：

- `ruff check .`
- `ruff format --check .`
- `pytest`
- Frontend 測試
- 空資料庫完整 Database Migration
- 本機關鍵流程
- Organization／Shelter A、B 隔離
- MinIO Adapter 測試
- GCS Adapter Contract Test
- Demo 資料掃描確認不含真實個資或正式收容所敏感資料

## Demo 元件

- Next.js Cloud Run Service
- FastAPI Cloud Run Service
- Background Worker／Job
- Cloud SQL for PostgreSQL
- Cloud Storage
- Secret Manager
- Artifact Registry
- Cloud Logging

## 部署後驗證

部署後必須重新驗證 Database Migration、Cloud Storage 權限、Signed URL、LIFF HTTPS、QR Code、Shelter A／B 隔離與 AI 失敗降級。Cloud SQL 連線、IAM、Service Account 與 Signed URL 行為不以本機通過作為證據。

## 資料限制

Demo 只使用虛構資料或合法公開資料；不可把本機 Seed Data 中的真實個資、正式收容所敏感資料或長效祕密帶入 Demo。
