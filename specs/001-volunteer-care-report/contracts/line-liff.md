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

## Webhook Session 與 Active Shelter Context

LINE Webhook 收到 `line_user_id` 後必須依序：

1. 查詢有效 LINE Binding。
2. Binding 無效時回覆 LIFF 驗證連結，不建立正式 Draft 或 Care Report。
3. Binding 有效時取得 `system_user_id`，查詢有效 Webhook Session。
4. 只有一個可用 Webhook Session 時，重新檢查 Shelter Membership 與權限。
5. 沒有可用 Webhook Session 時，查詢可用 Shelter Context；只有一個有效收容所才建立 Webhook Session。
6. 有多個可用 Webhook Session 或多個有效 Shelter Context 時，不自動選擇，回覆 LIFF 連結要求明確選擇。

Webhook Session 不得由 QR Code、Postback、裝置、GPS、IP 或時間重疊自動切換 Active Shelter Context。`PLATFORM_ADMIN` 使用平台級 `PLATFORM` Scope，不需 Shelter Membership；其跨收容所操作仍須由 FastAPI 驗證並留下 Audit Record。

## Rich Menu 與 Bot 回報

Rich Menu 至少提供開始照護回報、掃描 QR Code、今日照護毛孩、繼續未完成回報與聯絡工作人員。Rich Menu 只提供流程入口，不承載完整照護問卷。

Bot 每次原則上只詢問一個問題；Quick Reply 通常提供 3 至 6 個選項，適用時包含未觀察、無法判斷、略過或其他。Postback 使用穩定內部 Code，顯示名稱可變更但不得取代 Code。Bot 選項必須由 CRM 有效 Observation Vocabulary 產生或映射，不得硬編碼第二套業務選項。

Bot 使用 Server-side Draft 與受控狀態機；主要狀態依序為 `selecting_animal`、`confirming_animal`、`answering_completion`、`answering_feeding`、`answering_water`、`answering_activity`、`answering_elimination`、`answering_behavior`、`answering_special_status`、`awaiting_media`、`awaiting_note`、`reviewing`、`submitting`、`submitted`、`cancelled` 與 `expired`。`answering_completion` 依序詢問照護完成狀態與散步完成狀態；`answering_behavior` 依序詢問護食或資源防衛、對人的互動、對其他動物的互動、情緒與散步反應；`answering_special_status` 詢問外觀／特殊狀態。最終摘要確認前不得建立正式 Care Report；尚有任何標準回報必要答案未完成時，不得進入 `reviewing` 或 `submitting`。每名志工在單一 Organization 同時間只保留一筆 active Draft，重新進入時提供繼續、放棄或建立新回報。

標準回報必要答案包含 `care_completion`、`walk_completion`、`feeding`、`water`、`activity`、`urination`、`defecation`、`resource_guarding`、`human_interaction`、`animal_interaction`、`emotion`、`walk_reaction` 與 `appearance_special_status`。`care_completion.*` 與 `walk_completion.*` 的完成狀態，以及 CRM 有效 Observation Vocabulary 的其他穩定 Code，均視為答案；`not_observed`、`uncertain` 與 `walk_completion.not_done` 是有效答案，不是略過。照片與心得不屬於必要答案。

## 圖片訊息

收到 Image Message Event 後，先驗證事件、使用者、Membership、Active Shelter Context 與 Draft 狀態，再以 Message ID 取得 LINE Content。圖片必須完成檔案大小、MIME、實際格式、解碼、EXIF 移除、重新編碼與 Checksum，才可建立 Draft Media。原始圖片不得進入正式儲存空間或供 AI 讀取。取得或清理失敗時，提示重新傳送或略過，不阻擋文字與結構化答案。

## Mock 與真實環境

Application Layer 只依賴 `LineMessagingPort`。本機測試提供 Mock LIFF Context、Mock LINE Webhook Payload、Signature Test Helper、Mock LINE User、Rich Menu 範本、Postback／Image／Redelivery Fixture 與 `MockLineAdapter`，不呼叫真實 LINE API。

正式 `LineMessagingApiAdapter` 必須實作相同 Port，並負責：

- 使用 Reply Token 傳送 Reply Message。
- 在規格允許的補償情境傳送受控 Push Message。
- 依 Message ID 及時取得 Image Content。
- 驗證、建立、上傳與依環境綁定 Rich Menu。
- 將 LINE HTTP／API 失敗轉換為不洩漏內部資訊的受控錯誤，不回滾已保存的 Draft 或 Care Report。

Quick Reply 與 Postback payload 由後端 Presenter 依 CRM Effective Observation Options 產生，不由 Next.js 或 Adapter 硬編碼第二套業務選項。Channel secret 與 channel access token 只能由受控環境設定取得，不得出現在 log、Postback、Rich Menu action 或正式業務資料。

需要驗證真正 LINE Webhook、Rich Menu、Reply Token、Image Content、LIFF URL 或 LIFF Browser 行為時，使用官方建議的 HTTPS 本機開發方式或受控 Demo 入口。Rich Menu 由版本化環境設定與 `scripts/sync_line_rich_menu.py` 管理，發布流程必須可重複執行且不得把授權資料寫入 Action。

## LIFF 強制規則

1. LIFF Context 不是正式授權結果，CRM 必須重新判定使用者與 Organization Scope。
2. 舊畫面或快取資料不能覆蓋 CRM 現行資料。
3. 真實與 Mock 流程必須共用相同的回報確認、送出重新驗證與錯誤行為。
4. 未綁定使用者不得建立匿名正式回報。
5. LIFF 前端自行解碼的 LINE Profile 不得直接作為可信身分；FastAPI 必須向 LINE 驗證 Token／ID Token 後才建立本系統 Session。

## Adapter 驗證重點

- `MockLineAdapter` 與 `LineMessagingApiAdapter` 通過相同 Port Contract Test。
- 一般 unit／integration test 不連線真實 LINE API。
- Demo smoke test 驗證 Reply Message、Image Content 與 Rich Menu 發布／綁定。
- Reply 失敗不重複建立 Draft、Care Report 或 AI Job；Resume 仍可讀取 Server-side Draft 狀態。
