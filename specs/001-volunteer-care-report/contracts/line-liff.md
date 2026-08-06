# LINE Bot／LIFF 與 Mock Adapter 契約

## 通道邊界

LINE Bot 是志工日常照護回報的主要介面，使用 Rich Menu、Quick Reply、Postback、文字訊息、圖片訊息與 LINE Messaging API Webhook。LIFF 是輔助介面，用於第一次 LINE 身分綁定、QR／Deep Link 識別、完整動物確認、答案修改、長文字與 Bot 備援。

LINE Bot、LIFF 與 Next.js 不得自行建立正式 Shelter、Animal、Draft、Care Report 或 AI Job。FastAPI 是唯一 Authentication、Authorization、Organization Scope、Draft 狀態與 CRM 寫入邊界。

## Webhook 驗證與事件處理

1. FastAPI 必須以未修改的原始 Request Body、channel secret 與 `X-Line-Signature` 驗證 Webhook；驗證前不得解析、重排或修改 Body。
2. 簽章缺少或不正確時，不處理事件、不查詢 CRM、不下載圖片、不建立或更新 Draft、Care Report 或 AI Job；只留下不含敏感資料的 Security Event。
3. 每個事件依 `webhookEventId` 冪等處理，保存事件類型、處理狀態、Received At、Processed At、Failure Reason 與 Redelivery Flag。
4. Postback、Rich Menu Action、LINE User ID、`draft_token`、`step`、`value`、Animal ID 與 Message ID 都是候選輸入；後端必須重新驗證 Session、LINE User Binding、Membership、Active Shelter Context、Draft 與 CRM 關係。
5. Webhook 事件不得自動切換 Active Shelter Context；Organization 不一致時拒絕操作並保留既有 Draft。

## Rich Menu 與 Bot 回報

Rich Menu 至少提供開始照護回報、掃描 QR Code、今日照護毛孩、繼續未完成回報與聯絡工作人員。Rich Menu 只提供流程入口，不承載完整照護問卷。

Bot 每次原則上只詢問一個問題；Quick Reply 通常提供 3 至 6 個選項，適用時包含未觀察、無法判斷、略過或其他。Postback 使用穩定內部 Code，顯示名稱可變更但不得取代 Code。Bot 選項必須由 CRM 有效 Observation Vocabulary 產生或映射，不得硬編碼第二套業務選項。

Bot 使用 Server-side Draft 與受控狀態機；最終摘要確認前不得建立正式 Care Report。每名志工在單一 Organization 同時間只保留一筆 active Draft，重新進入時提供繼續、放棄或建立新回報。

## 圖片訊息

收到 Image Message Event 後，先驗證事件、使用者、Membership、Active Shelter Context 與 Draft 狀態，再以 Message ID 取得 LINE Content。圖片必須完成檔案大小、MIME、實際格式、解碼、EXIF 移除、重新編碼與 Checksum，才可建立 Draft Media。原始圖片不得進入正式儲存空間或供 AI 讀取。取得或清理失敗時，提示重新傳送或略過，不阻擋文字與結構化答案。

## Mock 與真實環境

本機測試提供 Mock LIFF Context、Mock LINE Webhook Payload、Signature Test Helper、Mock LINE User、Rich Menu 範本、Postback／Image／Redelivery Fixture 與 Mock LINE Adapter，不呼叫真實 LINE API。需要驗證真正 LINE Webhook、Rich Menu、Reply Token、Image Content、LIFF URL 或 LIFF Browser 行為時，使用官方建議的 HTTPS 本機開發方式或受控 Demo 入口。

## LIFF 強制規則

1. LIFF Context 不是正式授權結果，CRM 必須重新判定使用者與 Organization Scope。
2. 舊畫面或快取資料不能覆蓋 CRM 現行資料。
3. 真實與 Mock 流程必須共用相同的回報確認、送出重新驗證與錯誤行為。
4. 未綁定使用者不得建立匿名正式回報。
5. LIFF 前端自行解碼的 LINE Profile 不得直接作為可信身分；FastAPI 必須向 LINE 驗證 Token／ID Token 後才建立本系統 Session。
