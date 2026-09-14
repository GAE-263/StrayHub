# LINE 上線 Step 6：外部條件變更草案

2026-09-14。此文件是可審查的準備紀錄，不是 apply／dispatch 授權；T32–T36 尚未完成。

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

Repository 的 infra Terraform 搜尋未找到現行 provider resource；文件記錄曾啟用它，但不足以判定現行 authoritative ownership。**需維運者確認是其他 Terraform/IaC、其他 repository，或人工管理。** 在此之前不提供可誤用的直接覆寫命令，也不 apply。

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
