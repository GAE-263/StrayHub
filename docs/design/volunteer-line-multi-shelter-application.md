# 單一 LINE Bot／LIFF 的多收容所志工申請

## 架構

正式入口只有一個 LINE Bot 與一個 LIFF App。LIFF Console Endpoint 固定為
`/volunteer-application`，Bot 先讓使用者選擇收容所，再開啟 canonical LIFF URL：

```text
https://liff.line.me/<LIFF_ID>?organization_id=<UUID>
```

三個 demo 選項依序是：

- 毛小孩幸福聯盟協會（`FURKIDS-ASIA`）
- 新北市新店區公立動物之家（`MOA-SHELTER-51`）
- 新北市五股區公立動物之家（`MOA-SHELTER-58`）

畫面不顯示 UUID 或 code。LIFF query 只提供 target hint；status API 以資料庫中的
active organization 與 `OrganizationVolunteerAccessPolicy.applications_enabled` 驗證，
並回傳可信組織名稱。invalid／inactive／disabled target 顯示安全 unavailable 狀態。

## Target 與授權

`VolunteerTarget` 保證 status、submit、withdraw 都只能指定以下其中一種：

- `organization_id`：正常 Bot 選擇的公開申請目標。
- `shelter_entry_reference`：實體 QR、外部網站、海報或櫃台 QR 的 opaque target。

兩條路徑在 target resolution 後進入同一個 `VolunteerAccessService`。修改公開的
`organization_id` 最多只能向另一個 active 且開放申請的組織送出 pending application，
不會直接取得任何志工權限。實際授權順序維持：

```text
pending application
→ manager approval
→ OrganizationMembership(role=VOLUNTEER)
→ active VolunteerAccessGrant
```

repository、管理 API 與 RLS 仍以 organization scope 隔離 application、PII、服務日期、
membership 與 grant。

## Demo 與本機新身分

三個 demo 組織都 seed enabled policy，但不為正常 Bot 流程新增 entry-reference rows，
也不建立 `DailyReportableScope`。既有 `demo-furkids-volunteer`、
`demo-xindian-volunteer`、`demo-wugu-volunteer` 保留給 QR／照護展示。

本機 fake LINE channel 可使用 `local-id-token:<synthetic-subject>`。以每個組織不同的
synthetic subject 呼叫 status／submit，即可驗證 brand-new identity；資料不得使用真實
姓名、電話或 LINE user ID。status 不建立 identity，首次成功 submit 才由現有 service
建立 `User`／`LineUserBinding`。

## 狀態與未來強化

前端以 target key 重新載入 status，並在 target 改變時清除組織名稱、policy、服務日期、
表單與 pending state；舊 request 的回應不會覆蓋新 target。

V1 接受使用者修改 `organization_id` 後向任何 active + enabled 組織公開申請。若未來需要
綁定 Bot 選擇來源，可新增短效 signed application context（user、organization、purpose、
expiry）；目前延後，不影響既有 public-entry semantics。
