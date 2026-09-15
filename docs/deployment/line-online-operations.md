# LINE 上線操作與恢復

本文件描述本機完成、尚未對正式環境執行的工具。正式操作仍依
`line_bot_online_tasks.md` Steps 5–9 的授權順序執行；這份文件本身不授權遠端寫入。

## 分開核准的操作

| Operation | 作用 | 不包含 |
| --- | --- | --- |
| `config-sync` | 既有 atomic config-sync 載入 inert、bounded 或 global 配置；preflight 失敗會在持鎖期間還原 | 不 restart、不切 LINE 選單 |
| `reload-config` | 相同 deployed SHA／immutable images，重新載入 API、Worker、Celery 配置並等待 healthy | 不 build、pull、migration、refresh secrets、切換 release |
| `menu-switch` | default 單獨切換，或最多 20 位核准帳號逐筆切換個人選單 | 不建立／刪除資源、不授予 membership、不 bulk link |
| `menu-restore` | 從原始 private plan 與 receipt 產生精確恢復計畫 | 不處理原操作未碰過的人、不猜測角色、不廣泛 unlink |

Publication 保持原本獨立 workflow。新的 `line-online-operations.yml` 只有
`workflow_dispatch`，不接收 push／PR events。所有寫入要求雙 actor 都是 `yawan0203`、
attempt=1、repository=`GAE-263/StrayHub`、release ref，以及 requested／GitHub／checkout／
authoritative release HEAD 相同。WIF 前、SSH/IAP 前及 VM 首次 mutation 前重新核對；
每筆 LINE 切換前再次核對 authoritative release HEAD。VM deployed SHA 也必須相同。

新的 workflow identity 必須納入 Step 6 的 authoritative WIF ownership／claims 審查。
使用既有 production deployer 的受控 SSH 路徑；不在本機自動擴張 IAM 或 WIF。
若外部契約尚未允許此 workflow，保持拒絕，不能藉更寬的 provider 條件繞過。

## 計畫、敏感資料與 dry-run

Operator 在 VM root 擁有、0700 的 `/var/lib/strayhub/line-rollout` 保存：

- `manifests/<sha256>.json`：既有 publication 的 verified manifest，必須與 deployed SHA 相同。
- `plans/<sha256>.json`：prepare 產生的 canonical private plan，含當前 config hash、原綁定、
  精確目標、版本及時間；有效 24 小時。可能含 raw UID，不可放 Git／公開 artifacts／對話。
- `receipts/<plan-sha256>.json`：去識別 target hash、原／新 menu、寫入意圖及 readback。
- `requests/<sha256>.json`：受限非秘密配置。`evidence/` 保存受保護 schema 2 report/resources。

先由受授權的 operator 自動準備 protected request 與 verified manifest，再執行：

```bash
sudo -n /opt/strayhub/current/infra/gce/scripts/line-online-operator.sh prepare \
  --operation OPERATION --request PROTECTED_REQUEST_PATH --manifest-sha256 MANIFEST_SHA256
```

`prepare` 只對外 GET；不建立 LINE 資源或更改配置。stdout 只有 operation／SHA／plan hash。
Bot 身分、definition/image hashes 及現有個人／default 綁定會先讀回；只有 404 表示無 API
綁定，其他 API 錯誤都停止。hash 由工具計算，operator 接續使用輸出，不要求真人手算。
受保護 request 不得包含 secret；menu intents 格式為 `target` 與 `role`，role 只接受
default／volunteer，另附不含個資的 `authorization_source`。資料來源須是已核對的正式
資格／核准名單；工具不判斷或授予志工資格。未知綁定或資格必須列例外，不能推測。

Config request 使用 schema_version=1、mode、git_sha、manifest_sha256、channel_id；
bounded 額外接受 1–10 個不同帳號 SHA-256 及未來最多七天 expires_at。global 額外接受
受保護 report_path/resources_path，必須使用 schema 2 approved report。config-sync 再由
精確 API image 的完整 canonical preflight 驗證證據；dry-run 的結構驗證不等於 runtime PASS。
inert／bounded／global 都強制 Staff LINE=false。全域啟用後測試名單與期限可清空。
可明確提供 `ai`，只接受 boolean `celery_ai_enabled` 及 `gemini_model_name`；不能傳 key、
token 或 endpoint。真實 AI 憑證須先依 Step 6 授權備妥，canonical preflight 不允許
缺少必要憑證時啟用；global evidence 仍綁定受驗的 AI 設定。

每次使用新 dispatch，confirmation 精確為：

```text
LINE ONLINE <operation> <full-release-sha> <plan-sha256>
```

GitHub readback token 只經 SSH stdin 傳至 VM 記憶體，不放 shell arguments／檔案／receipt。
LINE 操作只讀取現有受保護 runtime secret generation，不存取 Secret Manager 或改 token。
使用固定 LINE hosts、endpoint allowlist、無 redirect／proxy／retry。不得以重跑 workflow
沿用授權。Private plan 及 receipt 不上傳 GitHub artifact。

## 證據核准與正式配置

`scripts.line_menu_smoke_evidence template --schema-version 2` 只建立 pending／NOT RUN。
集中手機測試後，工具協助填入真實觀察與來源；測試 fixture 不能當正式真人證據。
以同一 CLI 的 `approve`，提供既有 config／release manifest／resources／pending report、
新的 `--output`、opaque `--reference` 與 `--confirmation "APPROVE LINE EVIDENCE <report-sha256>"`。
它要求當下 scope 有效、所有真人／自動 case 已完成、版本與資源相符，才建立新 0600 report；
不把 NOT RUN 改為 PASS、不覆寫舊證據、不允許 revoked report 重新核准。
operator 欄位是受保護操作者的明確 attestation，不是數位簽章或登入驗證。

配置同步與 reload 必須分開產生計畫、分開核准。切換選單前會比對執行中 API 的
immutable image、healthy 狀態及作用中 scope/menu 設定；只改 production.env 無法通過。
bounded 模式不能改 default，只能操作名單內帳號。全域與 test access 仍由應用程式原有
簽章、身分與 tenant 驗證保護；此工具不改業務資料或角色。

## Runtime secret 讀取契約

Host operator 使用現有 `strayhub:strayhub` secret generation；不得以 `chown`
正式秘密檔案或放寬 plan／manifest 的 root-only 檢查來修復讀取失敗。
依本機 `strayhub` 帳號解析 UID/GID，root、generations 與 generation 目錄必須為
0700；runtime.env 必須是相同 owner/group、0600 的單一連結普通檔案。
只允許 current 指向 writer 產生的 `generations/YYYYMMDDTHHMMSSZ-xxxxxxxx`，
以 no-follow directory descriptors 固定讀取對象，拒絕額外 symlink、FIFO 與過大檔案。

Scalar 讀取不執行 shell、不展開變數，只解析 writer 的單引號格式及反斜線／單引號
跳脫；重複 key、空 token、換行與不合法格式均拒絕。錯誤只輸出
`credential_unavailable`，不包含 token、環境內容或 upstream response。
驗證使用合成 generation 與 token；實際部署後仍須重新執行唯讀 Bot／menu readback。

## 部分失敗與恢復

每筆 mutation 前將 intent 落盤，之後讀回實際 menu。中斷／timeout 保留
`intent-recorded` 或 `stopped-readback-required`，不重試，也不繼續其他帳號。
已存在 receipt 的計畫不能再 apply。先按該 plan 的精確清單 GET readback，再 prepare
新的剩餘工作或 menu-restore 計畫；新的時間與現況產生新 hash，重新核准 dispatch。
若現有綁定既不是原值也不是目標值，停止，避免覆蓋其他操作。

menu-restore request 只接受 `original_plan_sha256`，從受保護原 plan 與 receipt 產生。
原本無個人綁定時只 unlink 那一位；原本有綁定則恢復確切 menu ID。原 default 同理。
LINE 不提供這些同步 endpoint 的 compare-and-swap，讀回與寫入之間仍有外部競態；
操作窗口須避免其他管理員／流程同時切換同一帳號，工具不宣稱分散式原子性。

Config-sync 使用既有備份與 rollback receipt；失敗先確認原 checksum 已恢復。
reload-config 在 restart 前記錄 intent；失敗不能視為 runtime 已採用新配置，也不自動
deploy 或 rollback schema。讀取對應 compose 的 healthy／image／configuration 現況後，
再產生新計畫。Config-sync、reload 與 menu 操作使用同一 config lock 防止本工具交錯。

Release bundle 已收錄 host operator 所需的標準函式庫 Python 模組，避免 shell wrapper
存在但 import 失敗。API image 仍收錄 scripts，故 Step 5 的 clean-SHA image CI 必須覆蓋此變更。

平台 endpoint 依 [LINE Messaging API reference](https://developers.line.biz/en/reference/messaging-api/)
核對；同步操作沒有使用 bulk API、訊息推送 API 或資源刪除 API。

## 明確接受未驗收直接開放

schema 3 是獨立的 operator 授權路徑，並非 schema 2 真人驗收報告。
`human_validation` 固定為 `NOT RUN`，必須明確接受未驗收使用者流程，Staff/test
維持 false。授權綁定 release SHA、三映像 digest、Compose/bundle、Bot/Channel、
三角色選單及包含 AI 的設定 hash。既有登入、簽章、membership 與 tenant 邊界不變。

以 `line_menu_smoke_evidence direct-template` 產生 pending 文件；操作者確認後使用
`authorize-direct` 與 `AUTHORIZE DIRECT LINE OPEN <SHA> <pending-file-sha256>`，
產生新的受保護 immutable 授權文件。它不是測試成功證明，不能轉寫成真人 PASS。
正式 global config-sync/preflight 仍驗證完整授權與候選身分；同版本可正常 reload，
SHA/images/config/menu 改變時必須重新審查授權。撤銷文件後須 disable/reload 清除快取。
此路徑不自行切 default、遷移使用者、授予志工資格或啟用 Staff。

## Keyless Vertex AI runtime identity

Production Gemini can explicitly select `GEMINI_USE_RUNTIME_IDENTITY=true`,
`GEMINI_VERTEX_PROJECT` and `GEMINI_RUNTIME_SERVICE_ACCOUNT`. API and Celery use
Google Compute Engine metadata credentials with short-lived tokens. No local ADC
file, JSON private key, Secret Manager service-account key or GitHub credential is
used. Runtime identity takes precedence over legacy API-key/JSON settings and never
falls back after an identity or token refresh failure. Refresh runs off the asyncio
loop; errors contain only safe classifications. Legacy authentication remains for
existing local setups.

The attached VM account needs only model inference permission
`aiplatform.endpoints.predict` in the selected Vertex project. The production grant
uses `projects/canvas-primacy-502703-k1/roles/strayhubVertexPredictor`, containing only
that permission, bound to `strayhub-gce-sa@canvas-primacy-502703-k1.iam.gserviceaccount.com`.
This role/member was provisioned through the reviewed operator path; it has not
been imported into the retained platform Terraform state. API enablement,
billing/model availability and a synthetic real inference must be verified before
opening the AI features. The VM identity is shared by workloads that can reach its
metadata service; this is not container-level IAM isolation. Acceptance remains
AI-disabled and cannot enable this runtime mode through its safety preflight.

A reviewed rollout may provide `ai.runtime_identity` containing only `project` and
`service_account`. The exact identity participates in the opening report config
hash and runtime readback; changing identity requires new authorization evidence.
Configuration, deployment and LINE default/user switching remain separate fresh
manual operations. Never upload `service.json`, build it into an image, or print
credential values. Local `service.json` is excluded from Docker build contexts.
