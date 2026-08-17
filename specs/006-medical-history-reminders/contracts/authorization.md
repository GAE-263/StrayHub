# Authorization Contract

## 平台與收容所管理

組織生命週期與目前收容所業務管理是不同層級的權限。建立收容所會同時建立新的租戶與初始管理員，因此只能由平台管理員執行。

`PLATFORM_ADMIN` 不需要隸屬單一收容所；平台權限由 `/v1/auth/me` 的 `User.roles` 與 platform scope 表示。`LoginOrganization.role` 只表示使用者在特定收容所的 Membership role。

| 操作 | PLATFORM_ADMIN | SHELTER_ADMIN | STAFF | VOLUNTEER |
|---|---:|---:|---:|---:|
| 建立收容所與初始管理員 | 允許 | 拒絕 | 拒絕 | 拒絕 |
| 啟用／停用或跨收容所管理 | 允許 | 拒絕 | 拒絕 | 拒絕 |
| 管理目前收容所帳號／時區／區域 | 依平台 scope | 允許目前收容所 | 拒絕 | 拒絕 |

- 前端只對 `PLATFORM_ADMIN` 顯示建立收容所入口；隱藏按鈕不是安全邊界。
- 每次建立、啟用、停用或管理操作都由 API 重新驗證最新角色、active organization context 與 scope。建立／初始管理員／啟用／停用／跨收容所操作只允許 `PLATFORM_ADMIN`；目前收容所帳號／時區／區域操作只允許同 organization 的 `SHELTER_ADMIN`。
- 未授權建立請求必須在任何租戶、初始管理員或部分設定寫入前拒絕，且不得留下部分副作用。
- 成功與拒絕的組織生命週期操作都需留下 actor、時間、scope、結果及必要原因的 Audit。
- STAFF 可依既有 medical care capability 使用醫療功能，但不具收容所帳號、時區、區域或組織生命週期管理權限。

## 權限矩陣

| 操作 | SHELTER_ADMIN | STAFF + medical_care_access | STAFF 未授權 | 指派 VOLUNTEER | 其他 VOLUNTEER |
|---|---:|---:|---:|---:|---:|
| 完整醫療歷史／附件／Timeline | 允許 | 允許 | 拒絕 | 拒絕 | 拒絕 |
| 建立、更正、封存醫療紀錄 | 允許 | 允許 | 拒絕 | 拒絕 | 拒絕 |
| 建立／修改未來／停止提醒系列 | 允許 | 拒絕 | 拒絕 | 拒絕 | 拒絕 |
| 查看完整 Agenda／Calendar | 允許 | 允許 | 拒絕 | 拒絕 | 拒絕 |
| 完成／略過／改期／取消 occurrence | 允許 | 允許 | 拒絕 | 僅完成或略過自己的指派 | 拒絕 |
| 查看 assigned minimal projection | 不需要 | 不需要 | 不需要 | 允許 | 拒絕 |
| 授予 medical_care_access／改 timezone | 允許 | 拒絕 | 拒絕 | 拒絕 | 拒絕 |

SHELTER_ADMIN 的完整能力是 role policy，不依賴 capability 欄位。STAFF 每次 request 都重新檢查 active membership 與 capability。VOLUNTEER 不因 capability 欄位取得完整資料；只有 occurrence 的有效同收容所 membership 指派能授權 assigned endpoint。

## 租戶範圍

- organization scope 只取自 server 驗證後的 active context；任何 body／query／path 內的 organization hint 都不能擴張 scope。
- 每個 lookup 同時帶 `organization_id` predicate，資料庫再由 FORCE RLS 阻擋跨 tenant 存取。
- animal、record、series、occurrence、membership 與 media association 都重新驗 organization；不能只驗最外層資源。
- 跨 tenant、未指派及無權查看資源的回應不得洩漏內容、筆數、名稱或存在性；使用既有 generic not-found／forbidden policy。
- 前端導覽與 disabled 狀態只改善體驗，不是授權依據。

## 志工最小 Projection

assigned response 只可包含：

- `occurrence_id`、`version`、`status`；
- 動物名稱、完整收容編號及選填短效照片 URL；
- 提醒類型、標題、執行指示、預定本地日期時間；
- 本人是否可完成／略過。

不得包含 clinic、veterinarian、weight、醫療紀錄、附件、其他提醒、series 規則、其他負責人或完整動物 Timeline。Membership 被停用、指派改變、series 停止或 occurrence 結案後，必須重新套用目前 policy。

## 稽核與拒絕

建立、更正、封存、指派、series 變更／停止、完成、略過、改期、取消、capability／timezone 變更均寫 actor、time、source、operation id、before／after、reason／result。重要拒絕包含跨收容所識別、缺少醫療 capability、志工未被指派、membership／capability 已撤銷及對已結案事項的衝突提交，並在 business transaction rollback 後，以重新套用單一 organization scope 的獨立 terminal audit transaction 保存；Audit 不得反向洩漏不可見 resource payload。

既有 `GET /v1/management/audit` 對 `MedicalRecord`、`CareReminderSeries`、`CareReminderOccurrence` 與 `CareReminderAction` 的查詢，必須套用本文件相同的 medical capability，而不是只允許任意 STAFF role。醫療紀錄頁可用 `resource_type=MedicalRecord&resource_id={recordId}` 顯示只讀 before／after；未授權與跨 tenant 查詢不得回傳 Audit 內容或存在性。
