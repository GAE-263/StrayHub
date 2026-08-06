# 介面契約索引

本目錄定義本功能的外部與跨服務邊界。契約描述資料來源、授權、失敗處理與可觀察結果；不在本階段固定所有 Python 類別或完整程式實作。

`openapi.yaml` 是本 Feature 的 HTTP API Contract，包含 LINE Messaging API Webhook、LIFF 身分交換、Webhook Session 解析與 Bot 回報流程。LINE Webhook 是本 Feature 的正式輸入邊界；本目錄不建立獨立於 CRM 的通道資料來源。

- [OpenAPI Contract](openapi.yaml)
- [OpenAPI Contract Types 契約](generated-types.md)
- [CRM 與 Shelter 存取契約](crm-shelter-access.md)
- [Object Storage 契約](object-storage.md)
- [AI 非同步 Job 契約](async-ai.md)
- [LINE／LIFF 與 Mock Context 契約](line-liff.md)
- [GCP Demo 環境契約](gcp-demo.md)
