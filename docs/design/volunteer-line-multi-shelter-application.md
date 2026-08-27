# 單一 LINE Bot／Volunteer LIFF 的動態志工申請

## 責任邊界

正式入口只有一個 LINE Bot 與一個 Volunteer LIFF endpoint：
`/volunteer-application`。Rich Menu 的「志工報名」直接開啟 canonical LIFF URL，
不列舉縣市或收容所；「照護回報」維持既有流程，「我的申請」開啟同一 LIFF，
「領養媒合」目前由公開 postback action 回覆「功能準備中」，不包含媒合邏輯。

Volunteer LIFF 負責以下動態流程：

```text
公開目錄 → 選地區 → 選收容所 → 表單 → 確認 → pending／組織別狀態
```

## 動態公開目錄

`GET /v1/public/volunteer-organizations` 只回傳同時符合以下條件的組織：

- `Organization.status == active`
- `OrganizationVolunteerAccessPolicy.applications_enabled == true`
- `service_area` 可正規化為臺灣縣市

目錄只公開 region、organization ID、名稱與地址，不公開 code、policy metadata、
membership、聯絡祕密、稽核資料或 PII。V1 使用既有 `service_area` 作結構化縣市來源，
並在單一後端 helper 把「台」正規化為「臺」；不從地址猜測縣市。

目前 demo 只有「新北市」，底下為毛小孩幸福聯盟協會、新店動物之家、五股動物之家。
日後加入 active + enabled 且 `service_area=臺北市` 的組織，目錄會自動增加臺北市；
唯一符合資格的臺北組織停用後，臺北市會自動消失，Rich Menu 不需修改。

## Target 與授權

無 query 的正常 Rich Menu 流程由使用者在 LIFF 選取 `organization_id`。既有
`?organization_id=<UUID>` 外部連結仍可安全預選並略過選擇頁；invalid、inactive 或
disabled target 不會落回其他收容所，而是顯示 unavailable 並允許重新選擇。

`VolunteerTarget` 保證 status、submit、withdraw 只指定以下其中一種：

- `organization_id`：公開志工申請目標。
- `shelter_entry_reference`：實體 QR、外部網站、海報或櫃台 QR 的 opaque target。

兩條路徑在 target resolution 後進入同一個 `VolunteerAccessService`。修改公開的
`organization_id` 最多只能向另一個 active + enabled 組織送出 pending application；
它不是授權憑證。實際授權仍為：

```text
pending application
→ manager approval
→ OrganizationMembership(role=VOLUNTEER)
→ active VolunteerAccessGrant
```

application、PII、服務日期、membership 與 grant 由 organization scope 和 PostgreSQL
RLS 隔離。「我的申請」也必須先選取組織，不存在全域志工狀態。

## Demo、本機身分與狀態清除

三個 demo 組織 seed `service_area=新北市` 且 policy enabled，不為正常 Rich Menu
流程新增 entry-reference rows，也不建立 `DailyReportableScope`。既有三位 approved
demo volunteers 保留給 QR／照護展示。

本機 fake LINE channel 可使用 `local-id-token:<synthetic-subject>` 模擬無 membership、
grant 或既有 application 的新身分；使用合成姓名與電話。status 不建立 identity，首次
成功 submit 才由既有 service 建立 `User`／`LineUserBinding`。
當 `NEXT_PUBLIC_LIFF_ID=fake-liff-id` 時，Volunteer LIFF 會使用固定的合成 subject
`volunteer-liff-browser-demo`，因此本機瀏覽器可安全驗證新身分流程，且不會放行正式環境。

前端以 organization key 重建 application component；返回並選取另一收容所時會清除
可信組織資料、policy、服務日期、表單、submit、error 與 pending state，避免跨目標殘留。

## 本機 LINE／LIFF 實機驗證

`./scripts/test_line_local.sh` 驗證已由 `./scripts/demo.sh` 啟動的 API `8001` 與 Web
`3001`，按需啟動 host nginx `8082`，再以一條具名 ngrok tunnel 公開同一 origin。
nginx 保留 `/v1/*` 送 FastAPI，其他路徑送 Next.js；`/_next/*` 明確屬於 Web 並支援
WebSocket Upgrade，因此 HMR 不會誤送 FastAPI。瀏覽器的相對 `/v1` 也直接經 nginx
到 API，不需要 wildcard CORS。

helper 從 ngrok inspection API 依 tunnel name 解析 HTTPS URL，不解析 terminal UI；只
管理自己的 nginx/ngrok PID。它僅列出 LINE Developers 應填的 webhook、LIFF Endpoint、
`API_BASE_URL` 與不含 scheme 的 `LINE_DEMO_WEB_ORIGIN_HOST`，不會寫入 env、同步 Rich
Menu 或變更 LINE credentials。這個 local topology 用來先驗證未來單一來源 routing
模型，本項目不包含任何 GCP 部署或資源變更。
