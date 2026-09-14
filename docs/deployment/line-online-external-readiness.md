# LINE 上線 Step 6：外部條件變更草案

2026-09-14。此文件保留準備及執行紀錄。使用者後續明確授權六項前置變更，已完成並 readback PASS（見文末）；T32–T36 整體仍未完成，publication/deployment 未獲本輪授權。

## 凍結身分

- Repository：GAE-263/StrayHub。
- main：`e0ab761390809bcfc25f999a1bf68419758916fa`。
- release：`a3e206f9a553d75be9ac342ce73998ce1cf9badc`。
- Release push CI：34856253294，attempt 1，SUCCESS；本輪重新唯讀確認。
- Project：`canvas-primacy-502703-k1`，number `629644858010`。
- 本文件的本機 commit 不變更 candidate，不推送 main/release。

## 本輪唯讀證據與待批准差異

| 資源 | 本輪 readback | 提案與影響 |
| --- | --- | --- |
| Pool `github-strayhub` / provider `github` | ACTIVE；mapping 只有 subject、repository、ref、environment；條件仍允許 main/release 及舊 integration branch | 保留 provider。先確認管理來源，再收斂為本 repo、release、manual dispatch、核准 actor，並按 workflow/environment 配對；移除舊 branch/main 的寫入入口。不得直接覆寫未知共用來源 |
| Application publisher SA `strayhub-artifact-publisher` | workloadIdentityUser 綁定整個 release-publication environment | 改為 application publish 專用 workflow 身分，避免 LINE workflow 可 impersonate artifact publisher；保留現有 registry writer 的精確資源範圍 |
| Deployer SA `strayhub-gce-deployer` | workloadIdentityUser 綁定整個 production environment | 僅允許 gce-release 與 line-online-operations 的 production workflow 身分；不新增廣泛 compute/IAP 權限 |
| LINE SA `strayhub-line-menu-publisher` | describe NOT_FOUND | 建立專用 SA，無 user-managed key；只允許 line-rich-menu-publish workflow + release-publication impersonation |
| Bucket `canvas-primacy-502703-k1-strayhub-line-menu-manifests` | describe 404 | 建立前重驗名稱；location us-central1、私有、uniform access、public access prevention；依版本化設定 retention 31536000 秒，不鎖定 retention policy |
| LINE publisher 的 bucket 權限 | SA/bucket 尚不存在 | 精確 bucket 上只准 objects.create/get；不要使用含 list/delete/update 的寬鬆角色。既有 custom role 是否可重用及最終 role ID 尚待唯讀核對 |
| Secret `strayhub-prod-line-channel-access-token` | version 2 ENABLED；1 DISABLED | 固定使用 numeric version 2；只在此 secret 授予專用 SA payload access，不建立或旋轉 secret。IAM secret 範圍不等同 version 專屬 ACL；workflow 必須仍強制 numeric version |

WIF 精確配對提案（均為 `GAE-263/StrayHub/.github/workflows/<file>@refs/heads/release`）：

- `gce-release.yml` + release-publication → artifact publisher。
- `gce-release.yml` + production → deployer。
- `line-rich-menu-publish.yml` + release-publication → LINE publisher。
- `line-online-operations.yml` + production → deployer。

必須先確認 GitHub OIDC 實際可用 claims 及管理來源，再產出最終 mapping、condition、principalSet 和保留 etag 的 IAM 差異。不能假定 OIDC 有 triggering_actor claim；雙 actor、attempt=1、operation confirmation 與即時 release HEAD 檢查仍由 workflow/gate 強制，不以 WIF 取代。

Repository 的 infra Terraform 搜尋未找到現行 provider resource。後續 Admin Activity 查證已找到 gcloud 建立及修改紀錄（見下方 ownership 追查），可確認已觀察到的操作管理方式。沒有證據能保證其後從未被其他 IaC 納管；本次不為此讀取遠端 state，也不直接 apply。後續提案保留既有 provider，針對當下 readback 產出精確差異，需另外取得外部寫入授權。

## 授權後的順序與停止條件

1. 確認 WIF 管理來源，完成精確 IAM 差異、現有 policy/etag 備份及最小權限驗證。任一資源漂移停止；不廣泛替換 policy。不自動回復成過寬 trust。
2. 完成已核准的外部 prerequisites 後，新 dispatch `gce-release.yml`，ref=release、operation=publish、git_sha=上述完整 release SHA、confirmation=`PUBLISH a3e206f9a553d75be9ac342ce73998ce1cf9badc`。schema compatibility 保守使用 unknown，除非另有完整審查證據。
3. Publish 成功後自動讀取並驗證 run/artifact IDs、archive SHA-256、bundle SHA-256、三個 immutable image digests。這些目前不存在，不能從驗證型 build 推測或預填。
4. 以另一筆新 deploy dispatch 使用上述已驗證 receipt/artifact。確認正式 runtime 與設定仍符合前置條件，首次 global/test/staff 均 false。Deploy confirmation 包含候選 SHA 及實際 bundle hash；尚未產生的 hash 不作為授權證據。
5. 驗證 receipt、健康、workers、migration、AI 配置接線。歷史盤點中的 production 9d58 不是本輪 runtime readback；部署前必須重驗。現階段不得宣稱 real AI 可用。
6. 另行 LINE publication：同一 SHA，numeric secret version=2，confirmation=`PUBLISH LINE MENU a3e206f9a553d75be9ac342ce73998ce1cf9badc`。只建立／驗證／重用 default、volunteer、adoption_hub 並保存 immutable manifest；不切 default、不 link user、不建立 staff menu。

Publication、deployment、LINE publication 分開執行，不使用 rerun。未知 mutation outcome 先 readback，不盲目重試；失敗只提供完成狀態與精確恢復方案，rollback 必須另行授權。已建立 LINE 資源不刪除，bucket 不做廣泛清理。

## 尚需後續階段的事項

Bot/Channel/LIFF authoritative 對應、測試收容所與正常 Google/LINE 身分流程、bounded scope、真人手機驗收、真實 AI 成功、全域啟用及個人選單遷移仍未完成。它們不能由 CI、merge 或本草案代替。

本輪沒有 Secret Manager payload access、GCP/LINE mutation、dispatch、publish、deploy、config sync、restart 或正式業務資料寫入。

## WIF ownership 追查（2026-09-14）

- 維運者回覆目前不清楚管理來源；這不構成人工管理的證據。
- 本地 Git 可見歷史中，`a6f39ea0a42987b00c882edd8bad63155e0308e8`（2026-08-31）的首次發布紀錄已記載此 pool/provider 與兩個 service accounts，但沒有對應 provisioning 指令。
- 本地可見 Git 歷史的 Terraform/shell/Python 搜尋未找到此 provider 的管理宣告。查不到來源不代表其他 repository 沒有管理它。
- GCE local state serial 27 與 backup serial 25，僅提取 resource addresses 檢查，均無 workload identity pool/provider。未輸出完整 state 或資源屬性。
- Platform root 的 source、README、F5b adoption ledger 只列 secrets metadata/runtime IAM、KMS、backup/state buckets；未列 WIF。這是來源與歷史 ledger 證據，不能代替現行遠端 state。
- 遠端 platform state payload 讀取遭自動安全審核拒絕：完整 state 可能包含敏感資料，輸出過濾不足以消除讀取風險；命令未執行，未以其他工具繞過。
- 180 日 Audit Logs metadata 查詢持續未回應，已中止。後續縮小為 30 日 Admin Activity create/update metadata，設定 40 秒上限，成功返回 8 筆紀錄（四次操作各含 request/completion）。

| UTC 時間（request） | 指定 provider 管理事件 | Caller user agent 摘要 |
| --- | --- | --- |
| 2026-08-31T01:41:36.353263517Z | CreateWorkloadIdentityPoolProvider | gcloud 582.0.0、agent-name/codex_cli、providers.create-oidc |
| 2026-08-31T01:57:23.342946360Z | UpdateWorkloadIdentityPoolProvider | gcloud 582.0.0、agent-name/codex_cli、providers.update-oidc |
| 2026-09-03T06:54:46.509972894Z | UpdateWorkloadIdentityPoolProvider | gcloud 582.0.0、agent-name/codex_cli、providers.update-oidc |
| 2026-09-08T01:37:42.009066938Z | UpdateWorkloadIdentityPoolProvider | gcloud 582.0.0、agent-name/codex_cli、providers.update-oidc |

查詢限定本 project 的 cloudaudit.googleapis.com/activity、iam.googleapis.com、Create/UpdateWorkloadIdentityPoolProvider；只提取 timestamp、method、resourceName、caller user agent，未取得 credential、request payload 或完整 state。Update resourceName 精確對應 github-strayhub/providers/github；建立事件的 resourceName 為 parent pool github-strayhub。

結論：已觀察到的管理方式為 Codex/operator 透過 gcloud 建立及更新，未找到 Terraform 管理證據。這不是對所有未知外部 state 的完整排除。無需使用被拒絕的 state 讀取方式；下一步以既有 provider 的精確 mapping/condition 與 SA policy 差異作為審查標的，不重建 pool/provider。T32 仍未完成，所有外部 mutation 仍待授權。

## 精確變更提案與目前授權阻擋

[Cloud change plan](line-online-cloud-change-plan.json) 是純資料草案，包含完整 CEL mapping/condition、四組 principalSet、精確移除的兩個舊 environment members，以及新增 LINE SA／bucket／custom role／secret binding 的範圍。沒有執行器，也不代表 apply 授權。

本輪成功唯讀確認：pool 目前只有 github provider；project custom role list 為空；GitHub repository ID=1323840999、owner ID=313818911、yawan0203 actor ID=236169994。套用前仍須重讀，不能假定資源維持不存在。

提案在既有 repository/actor 名稱之外同時固定 numeric IDs；只接受 release、workflow_dispatch、attempt 1 與四組 workflow/environment 配對。新 release_route 以完整配對產生，其他一律 deny。LINE workflow 只取得 LINE SA，無法由同一 release-publication environment 取得 artifact publisher。

官方依據：[GitHub OIDC claims](https://docs.github.com/en/actions/reference/security/oidc) 列有 workflow_ref、event_name、actor/actor_id、repository IDs、run_attempt；未假設有 triggering_actor claim，後者仍由現有 workflow 強制。[Google WIF](https://docs.cloud.google.com/iam/docs/workload-identity-federation) 支援 CEL attribute mapping/condition 及 attribute principalSet；[deployment pipeline guide](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines) 說明指定 SA 的 workloadIdentityUser 綁定。未要求修改 GitHub OIDC subject template。

安全套用順序先移除精確舊寬鬆 binding，再改 provider，最後新增精確 binding；此間會短暫拒絕新的 workflow 認證。開始前必須確認沒有正在執行的寫入工作；已核發 token 不會因此立即撤銷。其他欄位／bindings 保留、policy 以 etag 防止覆蓋競態；不自動恢復過寬 trust。

新的 provider／SA policy／registry policy／secret policy metadata readback 遭自動安全審核拒絕，理由是早先明確禁止 WIF/IAM/Secret Manager 操作，後續「繼續」未明確撤銷。該批命令未執行，不改用替代工具。**下一個需要的授權僅為指定資源的唯讀 metadata 查證**，包括 project 內 pool bindings 的去敏檢查與權限 metadata；不包含 secret payload、Terraform state、IAM/cloud 寫入或 workflow dispatch。查證完成後才可提交最終外部 apply 授權範圍。

本機只做 JSON 結構與精確身分／路由一致性檢查，不宣稱已由 GCP 執行 CEL 驗證或完成真實 token exchange。未重跑大型 suite、未變更 runtime、未 push，候選 release 不變。

## 指定資源 metadata 查證完成（2026-09-14）

使用者明確授權上述唯讀範圍後，指定命令成功執行；先前 readback 阻擋已就此範圍解除，不代表外部寫入獲准。

| 指定資源 | 本輪結果 | 擬採動作 |
| --- | --- | --- |
| github provider | ACTIVE；原 mapping/condition 未漂移；issuer 為 token.actions.githubusercontent.com；oidc 未列 allowedAudiences | 只收斂 mapping/condition，保留 issuer/audience 行為 |
| Artifact publisher IAM | 唯一綁定為 release-publication environment 的 workloadIdentityUser；etag BwZaTeopDWY= | 精確替換成 app-publish 路由 |
| Deployer IAM | 唯一綁定為 production environment 的 workloadIdentityUser；etag BwZaTepS6g4= | 精確替換成 app-deploy、line-online 路由 |
| asia-east1/strayhub Registry IAM | runtime SA reader、artifact publisher writer；etag BwZaTen-iV0= | 保留，不修改 Registry IAM |
| LINE token secret IAM | 唯一直接綁定為 runtime SA secretAccessor；etag BwZaOcfRxzY= | 保留原 member，新增指定 LINE SA secretAccessor |
| LINE token versions | 2 ENABLED、1 DISABLED | 不讀 payload、不新增或旋轉版本；未證明憑證有效 |
| LINE publisher SA／manifest bucket | NOT_FOUND／404 | 僅在重新確認不存在後建立指定目標 |
| Project custom roles | 空清單 | 建立指定兩權限 custom role；不修改其他角色 |
| GitHub refs／runs | main/release 維持已記錄 SHA；in_progress、queued、waiting 清單均空 | 變更前再次檢查；此次不是永久無並行操作保證 |

這裡的 IAM 表僅描述指定資源的直接 policy，不是所有 inherited/effective permissions 的完整證明。全專案 service accounts 列舉及逐一 IAM policy 查詢被自動安全審核拒絕，因超出指定資源授權；該批命令未執行，不以其他工具繞過。未知其他 pool consumers 尚未排除。

下一個授權標的是 JSON 中的**前置資源與權限變更**：保留現有 pool/provider、收斂條件與指定 SA 綁定；建立指定 LINE SA、兩權限 custom role、私有 manifest bucket，新增指定 secret/bucket bindings。不包含 dispatch、credential payload access、publication、deployment、LINE API、config sync 或 runtime restart。

變更共用 provider 可能使未知但依賴舊 main/environment/branch 信任的工作無法取得新憑證；這是需審查的相容性影響。若尚未接受此範圍與影響，不得 apply。若執行時發現與 snapshot 不符或有進行中的寫入工作，停止而不自行擴權；不恢復過寬 trust。T32 仍保持未完成，直到實際變更與 readback 通過。

## 六項變更執行完成 — 2026-09-14 15:19 UTC

使用者明確表示「授權執行上述六項」。執行前所有 specified targets、policy etags、refs 與 workflow 狀態符合基準；在受保護目錄保存 before/after 與每個 IAM request，逐項變更後驗證，最後再次完整 readback。

| 變更 | 實際結果 |
| --- | --- |
| 既有 WIF | mapping/condition 精確符合 JSON proposal；issuer/audience 保留；GitHub actor/IDs、release、manual dispatch、attempt 1、四種 workflow/environment routes 已收斂 |
| 舊 environment bindings | 兩個精確 members 已移除；artifact publisher 僅 app-publish，deployer 僅 app-deploy/line-online |
| LINE publisher SA | 已建立，僅 line-publish federated binding；user-managed keys=0 |
| Manifest bucket | 已建立於 US-CENTRAL1，STANDARD、uniform access、public access prevention=enforced；retention=31536000 秒、未 lock；平台預設 soft-delete=604800 秒 |
| Custom role | `projects/canvas-primacy-502703-k1/roles/strayhubLineManifestPublisher`，GA，僅 objects.create/get；只在指定 bucket 綁定 LINE SA |
| Secret IAM | 保留 runtime SA，僅新增 LINE publisher 的 secretAccessor；version 2 enabled/1 disabled 未變；未讀 payload |

Registry IAM、main/release refs 未變。變更後未發現 in_progress、queued、waiting、pending、requested GitHub runs。這是查詢當下狀態；後續操作前仍重新確認。

原 proposal 保持不變，SHA-256 `ae15110c041a0fb7113caf8db10e732ae988d56f1838509a4ceacef583c452df`；其 PROPOSED 標記代表原審查版本，實際完成狀態以 [receipt](line-online-cloud-change-receipt.json) 為準。完整 policy 備份保留在 `/private/tmp/strayhub-cloud-prerequisites.1aynrfcg`，目錄 0700／JSON 0600，不含 secret payload。

限制：GCP 接受 CEL 且 readback 一致，但沒有執行 OIDC token exchange、實際 SA federation 或 LINE token validity 測試；未進行完整 inherited permissions audit。T32 的 IAM/資源部分完成，AI／部署前置與實際運作尚未證明。

未執行：push、dispatch/rerun、publication、deployment、LINE API、config sync、runtime restart、secret payload access、Terraform state access。恢復僅提供精確備份與已完成狀態，不自動恢復過寬 trust、不刪除資源；必要恢復需另外審查授權。
