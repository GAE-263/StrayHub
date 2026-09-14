# LINE 上線 Step 1：實際環境盤點

盤點時間：2026-09-14 13:05 UTC。此文件記錄唯讀觀察，不代表外部資源已全部就緒或已授權修改。後續 mutation 前重新 readback。

## 工作保存與版本

- Branch：`codex/staff-web-docs`；盤點起始 HEAD：`bafde674ed5ed2b44b242951cc7535459bde0ba9`。
- 六份文件已 staged，起始 cached binary diff SHA-256：`8cdd1efdbe6f3d039d38e0207a54e3df0d557810a803ae9f09f9aed6346b8924`；未改寫 staging 內容。
- 原始修改備份：stash object `a37979cbcb2788f5ec40735b929c8e74ecb7247e`，保留不刪。
- 遠端 main：`bafde674ed5ed2b44b242951cc7535459bde0ba9`。
- 遠端 release：`9d58d13e5ac634af9061288305bc548ec5e0ce8e`。
- PR #20：OPEN、Draft、CLEAN；base/head SHA 分別為上述 release/main。
- Production current：`/opt/strayhub/releases/20260910T013001Z-9d58d13e5ac6`。
- Production receipt：release SHA `9d58d13e5ac634af9061288305bc548ec5e0ce8e`，run `34425151708`，migration `0056_line_webhook_auth_scope`，verification=passed。
- API、Web、Celery Worker 顯示 healthy；Legacy Worker／Beat 正在運行，不能只由 Up 推論完整任務成功。公開 `/healthz` HTTP 200。

| Receipt image | Digest |
| --- | --- |
| API | `sha256:8d55b76f1c4b5cd5ced74df785de65efc276612528e0a46cab2d4edb01cb1231` |
| Worker | `sha256:a73393a768945e80c85b8b1f3aa6522ca4298262d2a67c28a1bbf9a0fa3cc1cc` |
| Web | `sha256:245ef827b791cbec20ab683714555693aeb46123db099c740f01fbf3f7583043` |

`docker ps` image ID 前綴與 receipt digest 相符；此盤點未替代完整 deploy receipt/runtime 驗證。

## 外部資源差異與阻擋階段

| 項目 | 觀察與分類 | 後續處理／阻擋階段 |
| --- | --- | --- |
| WIF provider | ACTIVE；mapping 僅 repository/ref/environment，未含 actor/event/workflow；條件允許 main/release 與 release-publication/production，另保留舊 integration branch | **設定不符完整目標契約**。先確認 authoritative IaC ownership，再提出精確 claims／binding 差異。發布前完成，不能直接覆寫共用 provider |
| Application publisher SA | 存在；environment=release-publication principalSet 有 workloadIdentityUser | 可重用；需收斂及核對完整 claims，非已完成所有安全驗證 |
| Application deployer SA | 存在；environment=production principalSet 有 workloadIdentityUser | 可重用；同上 |
| Artifact Registry | `asia-east1/strayhub` 存在，DOCKER；publisher 有 writer，VM SA 有 reader | 可重用，不另建 registry；publish 前重驗 |
| LINE publisher SA | 指定 `strayhub-line-menu-publisher` 回覆 NOT_FOUND，SA list 中亦不存在 | **缺少**；Step 6 經批准建立專用 SA 與最小綁定 |
| LINE manifest bucket | 指定 `canvas-primacy-502703-k1-strayhub-line-menu-manifests` describe 回覆 404 | **查無此目標 bucket**；Step 6 核對名稱可用性後建立，不更動其他 bucket |
| LINE token versions | version 2 ENABLED；version 1 DISABLED | numeric version 2 是待核准候選；未讀 Secret Manager payload，未驗證專用 SA access |
| Deployer IAP／OS Login | project 有限定 IP/port 的 IAP role；VM 有 osAdminLogin／viewer | 已有 binding。操作者經既有 SSH key、strict known-host 與 IAP 成功 `sudo -n` 唯讀；不等同證明 deployer 的完整 SSH／sudo 路徑 |
| AI | API 無 Gemini key/path；Celery Worker/Beat 有 Gemini key、AI flag=false；皆顯示 AI_PROVIDER=mock | **功能未啟用且 API 接線缺少**。Step 2 核對並補接線，Step 6 配置／驗證真實 provider；key 存在不代表可用 |

WIF 本次原條件摘要：repository 精確為本 repo，允許 main/release + release-publication/production，或舊 `codex/integration-adoption-growth-diary-d854237` + release-publication。未修改 IAM、provider 或資源。

## 正式 LINE 與 runtime

以既有 production API token 在 VM 記憶體內執行固定 GET；未輸出／保存 token 或 Bot raw UID，未呼叫任何 LINE 寫入 endpoint。

- Bot info：`@356imngb`，顯示名稱「浪浪森友島」。
- Webhook：`https://strayhub.enadv.quest/v1/line/webhook`，active=true。
- Runtime Channel ID：`2011250593`；LIFF：`2011171994-rPBlfJ1I`。
- Channel→Bot 的 Console authoritative 關係、LIFF endpoint/scopes、手機實際畫面仍未驗證；Bot info 不能單獨證明 Channel 關係。
- API／Legacy Worker `LINE_ROLE_MENU_FEATURES_ENABLED=false`，default/volunteer IDs 空；API hub/test/staff 設定尚未接線。
- API `CELERY_AI_ENABLED=false`；Celery Worker/Beat 同為 false，Gemini model 設定為 `gemini-3.5-flash-lite`；未進行付費 AI request。
- 現有 API default 指向舊資源 `richmenu-a5aa91d5c87ad984424dc51c1fc822f6`。

| 已存在資源 | ID | GET actions 結果 |
| --- | --- | --- |
| 新 default 候選 | `richmenu-5f482c5d00f85fff3cc964c6a10fa462` | volunteer application、open adoption hub |
| 新 volunteer 候選 | `richmenu-ae08bd235098852bb87770e2549dba1d` | walk report、return default |
| 新 adoption hub 候選 | `richmenu-fc5a2d52829ffe1b2cff09e7238614c4` | adoption matching、growth diary |

另有舊 default、volunteer（含 volunteer_checkin）、adopter、staff 資源。全部保留。本次未下載圖片或確認 candidate definition/image hashes，所以不能直接認定可重用；publication 必須完整 readback 後才判定，禁止依名稱重建或刪除。

個人綁定尚未查詢，因尚無核准的測試 UID／遷移清單。來源應以 server-side LINE identity binding、membership／有效 volunteer grant，加上每個已核准帳號的 LINE GET readback 交叉確認；不可用公開名稱或角色選單猜測身分。這是 Step 7/9 待辦，不將未知綁定視為無綁定。

## 精確後續方向與恢復邊界

1. Step 2–4 完成程式、證據與 operator 工具，不改正式環境。
2. Step 5 整合新 release；本次未改遠端 Git／PR。
3. Step 6 針對缺少的 SA/bucket 與不符的 claims 產生可審查差異；修改前保存 IAM policy/version，禁止廣泛替換或刪除。
4. Runtime 先維持功能關閉部署，再按 manifest 設定精確 IDs；啟用前保存 protected config checksum／backup。恢復須另行批准，不直接 rollback DB。
5. LINE 資源先完整驗證，promotion 前保存原 default／各帳號綁定；部分失敗先 readback，不批次 unlink、不刪舊資源。

尚未證明：實際 AI 成功、deployer 完整 sudo 路徑、Console/LIFF 身分、image hashes、個人遷移覆蓋率、真人功能驗收。Step 1 的完成僅表示盤點與缺口已記錄，非發布就緒。

## 本輪操作範圍

完成 GitHub/GCP metadata GET、既有 SSH/IAP 唯讀命令、LINE 固定 GET、公網 health GET。沒有 cloud/LINE mutation、Secret Manager payload access、dispatch、部署、config sync、資料庫業務寫入或 Acceptance 操作。原始 stash 保留；六份 staged 文件將留待 Step 2 commit。
