# LINE／LIFF 與 Mock Context 契約

## 通道邊界

Next.js 可接收 Mock LIFF Context 或真實 LIFF Context，但兩者都只能將使用者身分候選資訊交給 CRM 邊界驗證。通道不得自行建立 Shelter Scope、角色、Animal、Report 或 AI Job。

## Mock LIFF Context

本機測試至少能提供：

- 虛構使用者識別。
- 虛構 LINE 身分綁定狀態。
- 指定 Shelter Membership 與角色。
- 可切換有效、停用、未綁定與跨 Shelter 的測試案例。
- 不依賴 GCP 或真實 LINE 憑證。

## 真實 LIFF 驗證

只有需要驗證真正 LINE 身分、LIFF URL 或 LIFF Browser 行為時，才使用 LINE 官方 LIFF 開發工具提供的 HTTPS 本機開發環境或受控測試入口。Demo 階段另執行 LIFF HTTPS 驗證。

## 強制規則

1. LIFF Context 不是正式授權結果，CRM 必須重新判定使用者與 Shelter Scope。
2. 舊畫面或快取資料不能覆蓋 CRM 現行資料。
3. 真實與 Mock 流程必須共用相同的回報確認、送出重新驗證與錯誤行為。
4. 未綁定使用者不得建立匿名正式回報。
