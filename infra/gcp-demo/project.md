# StrayHub GCP Demo Project

本文件只描述可審查的 GCP Demo 邊界；T238 通過前不得執行 Terraform `apply`，也不得建立
或修改任何 GCP 資源。

## Project 與 Region

- Project ID：由 `terraform.tfvars` 或 `TF_VAR_project_id` 注入，不把正式 Project ID 寫入版本庫。
- Region：預設 `asia-east1`，由 `var.region` 注入。
- Environment label：`gcp-demo`。
- Terraform 唯一來源：`infra/gcp-demo/terraform/`。
- Backend：GCS backend 只在受控環境以 `-backend-config=bucket=...` 初始化；本機 Gate 使用
  `-backend=false`，避免意外接觸遠端 state。

## Demo 資料與通道

Demo 僅使用虛構的 `ORG-A`／`ORG-B`、`local-staff-a`／`local-staff-b` 與 Demo Animal。兩個
Organization 可以使用相同 Shelter Number，驗證後端租戶隔離；不得匯入正式收容所資料、LINE
User ID、真實姓名、照片或其他個資。

- LINE Channel：由 Secret Manager 的 `line-channel-secret` 與 `line-channel-access-token`
  Secret Reference 提供；本文件不保存 Channel Secret 或 Token。
- LIFF：由 `var.liff_id` 與 Cloud Run HTTPS URL 組合；不把正式 LIFF ID 寫入 Rich Menu。
- Rich Menu：版本化來源為 [`line-rich-menu.yaml`](line-rich-menu.yaml)，發布由
  `scripts/sync_line_rich_menu.py` 在受控 HTTPS 環境執行，不由 Terraform 管理。

## Service 清單

| 元件           | GCP 服務              | Service Account           | 主要責任                           |
| -------------- | --------------------- | ------------------------- | ---------------------------------- |
| Web            | Cloud Run Service     | `strayhub-demo-next`      | Next.js 管理／LIFF 介面            |
| API            | Cloud Run Service     | `strayhub-demo-api`       | FastAPI CRM、Webhook、授權與 Scope |
| Worker         | Cloud Run Service     | `strayhub-demo-worker`    | 非同步 Job 邊界                    |
| Migration      | Cloud Run Job         | `strayhub-demo-migration` | 受控 Cloud SQL Alembic Migration   |
| Database       | Cloud SQL PostgreSQL  | Migration／Runtime Roles  | CRM 唯一事實來源                   |
| Object Storage | Private Cloud Storage | API／Worker               | 清理後媒體與 Signed URL            |
| Image          | Artifact Registry     | GitHub OIDC               | 映像保存與建置輸出                 |
| Logs           | Cloud Logging         | Runtime Service Accounts  | 不含 Secret 的集中式觀測           |

## Secret 與禁止事項

Terraform 只接收 Secret 名稱 Reference，不接收或輸出 Secret 明文。以下 Secret 必須在受控
部署前由 Secret Manager 管理：

- `database-url`
- `database-password`
- `line-channel-secret`
- `line-channel-access-token`
- `auth-jwt-active-private-key`
- `auth-jwt-active-public-key`
- `animal-confirmation-secret`

### Volunteer PII encryption

The API uses Cloud KMS for volunteer PII in GCP Demo. Terraform receives an
existing CryptoKey resource name through `var.pii_kms_key_name`; it never
creates, imports, or stores key material. The API Cloud Run revision sets:

```text
PII_ENCRYPTION_PROVIDER=gcp-kms
PII_KMS_KEY_NAME=<existing CryptoKey resource name>
```

`strayhub-demo-api` receives only
`roles/cloudkms.cryptoKeyEncrypterDecrypter` on that one CryptoKey. The worker,
web service, migration job, GitHub OIDC principal, and project members do not
receive KMS decrypt permission through this configuration.

Cloud KMS receives the existing field-scoped additional authenticated data:
organization ID, application ID, field name, and PII schema version. The
database stores KMS ciphertext, provider algorithm, and the returned CryptoKey
version only. Plaintext, raw ciphertext, and key material must not be put into
logs, audit payloads, Terraform state, Secret Manager, Docker images, or
frontend variables.

The local AES provider is for `local`/`test`/`testing` only. It is fail closed
outside those environments and the KMS adapter never falls back to it. A
missing/invalid key resource, KMS permission failure, or KMS outage returns a
safe 503 without persisting plaintext or returning revealed data.

### KMS key rotation and staging validation

Rotate the primary version of the same CryptoKey using the approved KMS key
rotation procedure. Stored metadata records the KMS CryptoKeyVersion used for
encryption; decrypt requests stay bound to the configured CryptoKey, allowing
KMS to decrypt old-version ciphertext while that version remains enabled. Do
not disable an old version until retained PII using it has expired or been
re-encrypted by a separately approved operation.

Before directing staging traffic to the new revision, use only a synthetic
organization and synthetic applicant values to verify:

1. synthetic application submission creates encrypted profile columns;
2. same-organization shelter admin reveal succeeds and writes metadata-only audit;
3. wrong organization/context and unavailable KMS both return safe errors;
4. audit failure returns no plaintext; and
5. KMS/audit/application logs contain neither plaintext nor ciphertext.

Record pass/fail and redacted request identifiers in deployment evidence. Live
KMS validation is not satisfied by a fake client or local AES test.

禁止事項：

1. 禁止將 Secret、JWT Private Key、LINE Token、Signed URL 或正式個資寫入 Git、Docker image、
   Terraform source、Rich Menu、CI log 或 application log。
2. 禁止在 T238 前執行 `terraform apply`、Cloud Run YAML 部署或建立 GCP 資源。
3. 禁止使用 `cloud-run-*.yaml` 作為正式部署來源；Cloud Run、IAM、Cloud SQL、GCS 與 Logging
   必須由 Terraform 宣告。
4. 禁止把本機 MinIO、Mock LINE、Fake AI 或本機通過結果當成 GCP 專屬驗證證據。
