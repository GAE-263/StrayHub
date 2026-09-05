# 開發者快速手動測試流程設計

狀態：已實作本機啟動、LINE 開發模式、doctor 與 password 指令。下列章節保留設計目的，
具體操作以 README 的「開發者手動測試」為準。

實作注意事項：首次完整資料下載仍需網路；既有資料不完整時不會自動重跑 seed，
而是提供 `demo.sh check` 作為明確重新初始化入口（該操作會重新設定 demo 資料及密碼）。
每次會執行 Alembic upgrade head 與 runtime ACL 檢查／補齊；已套用的 migration 不會重跑。
doctor 檢查工具、Docker、設定與連接埠，不代表已通過真實 LINE 對話驗收。
金鑰保存於 `.env.dev-keys.json`；前端 lockfile 摘要保存於 `.env.dev-state.json`；
兩者由既有 `.env.*` Git ignore 規則排除。一般重啟無須再提供密碼。

## 使用體驗

開發者完成一次初始化後，平常只需啟動服務、開啟測試入口、操作功能。
密碼、操作者代號、ACTIVATE 與公開分享驗收不應成為每次本機測試的步驟。

| 目的 | 指令 | 測試入口 |
| --- | --- | --- |
| 測網頁、角色權限、平台管理 | `./scripts/dev.sh` | 本機管理介面 |
| 同時測真實 LINE Bot／LIFF | `./scripts/dev.sh --line` | 本機完整管理介面＋LINE 公開入口 |
| 檢查環境與服務狀態 | `./scripts/dev.sh doctor` | 終端機顯示故障與下一步 |
| 忘記開發密碼 | `./scripts/dev.sh password` | 隱藏輸入新密碼，明確更新 demo 帳號 |

保留 `demo-shared-management.sh` 給外部測試者的公開分享情境。開發者不需要選擇
production/dev profile 或手動準備 activation evidence。

## 第一次執行

1. 先檢查必要命令、Docker 狀態、連接埠，以及本機資料庫與儲存位置；問題集中列出。
   只測網頁時不要求 ngrok、nginx 或真實 LINE 設定。
2. `.env` 不存在才從範本建立；已有設定保留。依賴缺少時執行既有 uv／npm 安裝流程。
3. 只詢問一次開發密碼（至少 16 字元），建立或明確初始化 demo 帳號。
   若偵測到既有 demo 資料，沿用帳號與密碼，不自動輪替。
4. 啟動既有 Compose PostgreSQL／MinIO，執行必要 migration、runtime-role 設定與資料初始化。
   沿用三收容所 demo 資料；首次下載照片／MOA 資料顯示進度與失敗重試方式。
5. 啟動 API、前端與 worker，健康檢查通過後顯示登入網址與角色帳號。

密碼雜湊沿用資料庫保存方式，不新增明文密碼檔案，不在指令輸出顯示密碼。
本機 JWT 與 PII 金鑰需一次建立並持續沿用，放在權限受限、Git 忽略且不對外服務的
本機設定目錄；已有資料時保留既有金鑰，不因缺少設定而任意產生替代金鑰。

## 日常啟動

`./scripts/dev.sh` 使用前端 dev server 與 API reload。資料與帳號存在時跳過 seed、
密碼輪替及 session 撤銷；依賴 lockfile 或 migration 有變化才做必要更新。
一般啟動只檢查必要資料和服務可用性，完整照片驗證與資料更新留給明確維護指令。

不得以單一「初始化完成」檔案取代資料庫檢查。若部分資料缺失，提供可重跑的修復方式，
保留開發者已建立的動物、問卷、領養草稿、LINE 綁定與權限變更。

啟動完成輸出範例：

```text
開發環境已就緒
管理介面：http://127.0.0.1:3001/login
API 文件：http://127.0.0.1:8001/docs

收容所管理員：demo-furkids-admin（FurKids／新店／五股）
平台管理員：demo-platform-admin（平台治理）
志工：demo-furkids-volunteer／demo-xindian-volunteer／demo-wugu-volunteer
密碼：沿用初始化時設定的開發密碼

停止：Ctrl-C；資料保留
```

登入仍使用既有帳號密碼 API。選擇測試角色不直接修改 session、membership 或前端權限。
平台管理員不因角色取得所有收容所 membership。

## LINE 測試

`./scripts/dev.sh --line` 在相同 API／前端／worker 上加開 nginx 與單一 ngrok tunnel，
重用既有 `line-only` allowlist。管理介面保持本機使用，手機使用 HTTPS LINE／LIFF 入口。

第一次才需配置 ngrok 固定網址與授權、Messaging API 憑證、LIFF ID 及 LINE Login Channel。
缺少設定時列出欄位名稱與 Console 設定指引，不輸出 secret。輸出 webhook URL，
並依目前 LIFF 功能提供正確 Endpoint；不沿用文件中可能過時的固定路徑。
收容所入口代碼只在使用需要它的邀請入口時要求，公開領養入口不應要求手動填寫該代碼。

重啟後沿用已建立的 LINE 身分與測試流程。需要測「全新使用者」時，另行指定要重置的
本機測試身分與範圍，不能在每次啟動時清除所有人的狀態。

Webhook 簽章、重複事件處理、圖片 token 與收容所隔離照常驗證；不因開發模式跳過。
手機不經由 LINE tunnel 取得平台治理頁面。需要外部分享管理工作台時使用既有分享流程。

## 啟動失敗與停止

- 提示具體故障，例如「Docker 尚未啟動」「API 8001 被其他程序使用」「LIFF 缺少 Login Channel ID」。
- 只管理本 helper 建立的程序；重複啟動可顯示既有入口，辨識不到擁有者就報告衝突。
- 任一服務失敗即清理本次已啟動的應用程序，不留下半套 tunnel。
- Ctrl-C 停止應用程序與 tunnel，保留 Compose 資料服務及資料 volume。
- 日誌遮蔽密碼、token、entry reference，失敗時提供服務名稱及可用的去敏診斷。

## 現況差異與實作落點

- `demo-shared-management.sh` 目前每次詢問密碼／操作者／ACTIVATE 並建立暫存 evidence，
  適合公開分享的用途，不作為日常開發入口。
- `demo.sh`／`bootstrap_demo.py` 每次呼叫 seed；`seed_demo_accounts.py` 輪替帳號密碼並
  撤銷 session。需分離「初始化」「啟動」「明確重設密碼」，不能僅在外面包一層腳本。
- `demo-line.sh` 已有程序清理、公開 URL 與 gateway 產生邏輯，應抽取或擴充既有共用部分，
  不複製第二套 tunnel 管理與路由政策。父程序統一載入設定／金鑰再交給子程序。
- `AppSidebar.tsx` 的 public management 模式只有總覽、動物檔案、回報收件匣、
  照護行事曆、AI 人工覆核；`SessionService` 拒絕 public profile 的平台管理員登入。
  本機管理入口應取得正常 local session，不能帶入公開 profile。
- 目前 `SessionService.login` 已在驗證平台身分後切換 platform RLS scope。
  新增整合測試以 `SET LOCAL ROLE strayhub_runtime` 驗證無 membership 的平台帳號登入與
  組織清單，並確認同一帳號在公開 shared profile 仍被拒絕。
- 首次 MOA 下載仍可能慢或失敗；初版如實顯示進度。離線小型資料集屬後續擴充，
  不在開發者不知情的情況下把正式 demo 資料換成測試 fixtures。

## 驗收條件

1. 全新本機按提示完成一次初始化後，第二次執行沒有互動問題，既有密碼與登入維持可用。
2. 日常重啟不重新匯入 MOA、不重設問卷、不刪除 LINE 綁定，不覆蓋測試中的角色權限。
3. 本機平台管理員可登入平台治理；收容所管理員可切換三個授權收容所且資料不混用。
4. `--line` 可接收真實簽章 webhook、載入 LIFF 與圖片，本機完整管理介面同時可用。
5. LINE 公開網址無法開啟管理／平台治理入口；偽造 profile、跨收容所存取仍被拒絕。
6. 程序失敗與 Ctrl-C 不殘留本次 tunnel，也不停止其他工作使用的程序或刪除資料。
7. 密碼重設明確執行且撤銷舊 session；一般啟動不會悄悄執行同樣操作。

實作依序完成本機啟動與帳號持久化、平台登入驗證、LINE 模式、整合入口文件；
以 targeted helper 測試、登入／租戶隔離回歸及一次真實 LINE 操作確認行為。
