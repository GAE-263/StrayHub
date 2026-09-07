# 加入收容所申請調整

## 規格

使用者透過固定 `/account?join=<organization UUID>` 連結登入並確認收容所後送出申請，不輸入邀請碼。管理員核准當下選 STAFF 或 SHELTER_ADMIN；否決從待審清單移除，保留本人結果、處理人、時間及稽核。User 與其他收容所 membership 不刪除。志工與平台角色沿用原流程。

## 設計

新增 OrganizationJoinApplication，使用既有 InvitationService 的管理授權及 membership service。pending 唯一索引限制同一人同一收容所僅一筆；每組申請以 advisory lock 序列化，否決後一天才能重送。核准以現有收容所鎖及申請列鎖確保角色名額及原子性。

固定連結不是 capability；只允許已登入者以精確 UUID 查詢啟用收容所名稱。資料庫函式僅回傳 ID／名稱，函式內暫用既有租戶 scope 並還原；不新增組織清單或放寬既有 RLS。申請表本人 SELECT／INSERT、租戶管理 UPDATE，禁止 runtime DELETE。

0051 migration 把未到期已認領邀請轉成 pending（同人同收容所取最新一筆），原 open／claimed 邀請關閉；已核准 membership 保留。舊建立／認領 API 回 410 並提示新流程，舊清單與歷史保留。回滾 migration 會刪除新申請資料，應先備份，不還原已失效邀請。

## 任務

- [x] 新模型、migration、RLS、過渡處理。
- [x] 本人申請、精確名稱查詢、管理員審核與稽核。
- [x] 固定連結、登入後續接、申請及審核頁面。
- [x] 同步契約、測試與開發驗收文件。

## 驗證結果

聚焦後端 13 passed，涵蓋申請、重複送件、RLS 本人越權寫入拒絕、pending 唯一約束、跨收容所審核拒絕、非法角色拒絕、否決／重送冷卻、重複審核拒絕及 Google 認證回歸。保留原測試金鑰的一項 HMAC 長度警告。

前端 21 passed，包含 Google callback 保留申請目標、原帳密頁與 proxy。Chromium 3 passed，涵蓋固定連結登入續接、本人送件狀態及管理員選角色核准／否決。TypeScript、production build、契約產生檢查、Ruff check 及 diff whitespace 檢查通過。

僅專用 `strayhub_test` 執行 0051 migration；一般開發 DB 尚未由本次操作套用。可先停止開發服務，再執行 `./scripts/dev.sh`，既有 helper 會先升級 migration 才啟動。Migration 的舊邀請轉換邏輯已檢視，但未對使用者實際邀請資料演練。新流程沒有重跑完整歷史 suite，既有失敗紀錄仍見 validation.md。

否決申請保留最小紀錄與 audit；實際保存期限沿用尚待產品確認事項。沒有新增可公開列舉組織的 endpoint。函式 EXECUTE 僅授予 runtime，runtime 不可 DELETE 申請資料。原 staging 保留，本次修改留在工作目錄。
