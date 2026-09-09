# Google 身分與本人帳號入口

設計來源：[google_auth.md](../../google_auth.md)。2026-09-07 使用者授權補文件並開始實作；不包含雲端設定、commit 或部署。

## 驗收需求

1. GIS 官方 popup 按鈕取得 token，由後端驗章、issuer、audience、時間與 nonce 驗證後簽發既有 session。
2. 登入交易短效、一次性、綁定瀏覽器；link 交易要求原帳密重新驗證及同一 session。
3. Google sub 唯一，首次註冊需明確選擇建立帳號及顯示名稱；不存 email，不自動合併，不授予角色。
4. 本人帳號頁在沒有或失去 membership 時仍可使用；業務 endpoint 仍強制 tenant authorization。
5. 管理者建立邀請碼，使用者認領，管理者確認後才建立 membership；保留兩名管理員上限及原角色限制。
6. 保留帳密、LINE／LIFF、公開 profile 與 tunnel 邊界。
7. 綁定不改 user_id；解除須驗證保留的密碼並撤銷全部 session；Google-only 不可解除。
8. 註冊與權限變更具原子性、RLS／ACL 與去敏 audit。不得使用平台 scope 代替本人授權。

## 治理與範圍

User 為既有全域登入身分；OrganizationMembership 為租戶資格，不允許跨租戶業務讀寫。此解釋遵循使用者明確要求的一人多收容所，未修改憲章。

功能預設關閉。正式啟用前須確認對外隱私告知、保存政策及 origin。測試只使用專用本機測試資料庫；不執行一般開發資料庫 migration。
# 加入申請流程更新

現行加入流程以 [application-review.md](application-review.md) 為準：固定申請連結、本人送件、管理員選角色核准或否決；上方邀請相關敘述保留為原始版本背景。
