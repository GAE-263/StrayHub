# 研究：志工角色導向入口與管理路由隔離

**功能**：[spec.md](spec.md)

**研究日期**：2026-08-14

## 決策 1：使用不掛載 children 的 client route boundary

**決策**：在 `apps/web` 建立共用 authenticated route boundary。Boundary 在 client 端先讀取既有 access token，再向後端取得目前使用者與 Active Shelter Context；判定完成前只呈現安全的 loading／status，不掛載管理或志工 page children。

**理由**：

- 現有 access token 儲存在 sessionStorage，Next middleware 與 Server Component 無法取得，若強行使用 server redirect 就必須同時遷移 auth storage，會超出本功能範圍。
- 只在 child 掛載前完成判斷，才能保證 Dashboard effect、管理資料查詢與管理畫面不會先執行或短暫顯示。
- 管理與志工 route group 可以共用 Session／Context 驗證及有限狀態，減少 redirect loop 與錯誤文案分歧。

**考慮過的替代方案**：

- **Next middleware 依角色 redirect**：不採用；middleware 目前無法取得 sessionStorage token，引入 cookie session 是獨立的 authentication migration。
- **每個 page 自行 useEffect redirect**：不採用；child 已掛載並可能先發出資料查詢，也會複製角色與錯誤處理。
- **只隱藏管理 Sidebar**：不採用；無法阻止 Dashboard 與 deep-link page 查詢，也不是安全邊界。

## 決策 2：有效角色由後端 profile 與 Active Shelter Context 推導

**決策**：登入完成後使用已選定的 `organizations[].role` 決定第一個 route；deep link、reload 與 browser back 則使用 `/v1/auth/me` 及 `/v1/auth/active-shelter-context` 重新推導 `EffectiveRole`。`PLATFORM_ADMIN` 優先於 Membership；其餘使用者只採目前 organization 的 active Membership role。

**理由**：

- Login response 已提供每個可選 organization 的後端角色，可在 context switch 成功後立即決定 `/` 或 `/animal-confirmation`，不需額外查詢。
- `/auth/me` 提供 `platform_role` 與 Membership；Active Context 提供目前 organization，兩者組合可處理 direct URL、重新整理與角色撤銷。
- sessionStorage 中的 organization id／code 只用於既有顯示 cache，不能成為角色或 scope 來源。

**考慮過的替代方案**：

- **只相信 login response 並永久保存 role**：不採用；Membership 或 Session 狀態可能在 reload 前改變。
- **由 pathname 推測角色**：不採用；網址不是權限來源。
- **先呼叫管理 Dashboard 以 403 判斷志工**：不採用；違反「不先發出管理查詢」與低摩擦目標。

## 決策 3：管理資料 request 必須排在角色判斷之後

**決策**：管理 route 的固定順序為：檢查 token → 同批取得 profile 與 Active Context → 推導有效角色 → 志工導回／錯誤終止，或管理角色繼續 → 取得 organizations → 掛載 Management Shell 與 page children。志工路徑不得發出 `/v1/management/*` 或任何管理 page-specific request。

**理由**：

- 現有 `ManagementLayout` 同時取得 profile、context 與 organizations，`/` 的 `ManagementHome` 又會在外層 gate 判定前執行 Dashboard effect。
- 先完成最小 profile/context 判定，能避免 volunteer deep link 取得管理摘要、筆數或 detail request。
- management role 通過後才載入 organizations，不會改變工作人員與管理者的 context selector 行為。

**考慮過的替代方案**：

- **保留所有並行 request，再忽略結果**：不採用；仍會產生不必要管理查詢，也擴大資料暴露面。
- **只阻擋 Dashboard render**：不採用；network request 已經發生，其他 deep link 仍有相同問題。

## 決策 4：將 `/` 納入 `(management)` route group

**決策**：實作時由 `apps/web/app/(management)/page.tsx` 接管 `/`，並讓 `management-home.tsx` 只渲染 Dashboard content，不再自行包 `ManagementLayout`。所有管理 route 由 `(management)/layout.tsx` 一次套用 route boundary 與 Management Shell。

**理由**：

- `/animals`、`/reports`、`/settings/*` 與 `/shelters` 已在同一 route group，只有 `/` 位於 group 外，造成兩種不一致的掛載順序。
- route group 不改變 URL，可保留 `/` deep link 與現有管理使用者行為。
- 統一 layout 後，Dashboard child 不會在 boundary 回傳 loading／redirect 時掛載，因此可驗證 Dashboard request 為 0。

**考慮過的替代方案**：

- **在 `app/page.tsx` 再包一個獨立 guard**：不採用；會形成第二套管理入口 composition，容易再次重複 profile/context 查詢。
- **保留 `ManagementHome` 內層 layout**：不採用；child effect 的生命週期無法由內層 layout 阻止。

## 決策 5：志工 route 驗證 Session／Context，但不新增反向角色封鎖

**決策**：新增 `(volunteer)/layout.tsx`，在 `/animal-confirmation` 與 `/care-report` 掛載前驗證 Session 與 Active Shelter Context。志工角色可進入；管理角色若直接開啟志工輔助 route，仍沿用既有後端權限，不由本功能新增禁止規則。管理角色登入後的預設入口仍是 `/`。

**理由**：

- 規格要求志工 route 必須先有有效 context，且 session 失效時前往 `/login`。
- 既有後端允許被授權工作人員使用部分回報流程；本功能只隔離「志工不能進管理 route」，沒有授權封鎖管理角色使用志工輔助流程。
- Boundary 不掛載 child，可避免在 context 驗證前先查詢動物或草稿。

**考慮過的替代方案**：

- **只在 management layout 加 guard**：不採用；無法處理直接開啟志工 route 時的 session/context 缺少。
- **管理角色一律從志工 route 導回 `/`**：不採用；會新增規格未要求的反向限制，可能破壞既有工作人員回報能力。

## 決策 6：P0 沿用單一 current draft contract

**決策**：P0 在 route boundary 通過後，由 `/animal-confirmation` 組合既有 `/v1/animals` 與 `/v1/line/care-report/drafts/current`。Current draft 為 null 時直接顯示動物確認；有 active、未過期且 animal 仍在今日可回報名單的草稿時顯示「繼續回報／稍後處理」。繼續後前往既有 `/care-report`，由該頁沿用目前草稿恢復流程。

**理由**：

- 既有 domain 與 tests 明確限制每位志工、每個 Active Shelter Context 最多一筆 active draft。
- Current draft endpoint 已由後端按使用者與 organization scope 查詢，並有既有 resume／expire 驗證；不需要新增 API 或資料模型。
- 與今日名單比對可以提供動物名稱／收容編號，同時避免對已不可回報或不在 scope 的動物顯示詳細草稿資訊。

**考慮過的替代方案**：

- **使用 OpenAPI 中的 draft list 做多筆 P0 選擇**：不採用；原始需求把多筆策略放在 P1，而且現有 domain 只允許單一 active draft。
- **登入後直接自動前往 `/care-report`**：不採用；使用者沒有明確選擇，且會讓登入動作意外改變目前工作脈絡。
- **把 draft id 存進 sessionStorage 作為恢復依據**：不採用；client state 不是授權來源，也可能在 context 切換後殘留。

## 決策 7：使用有限 route state 防止 redirect loop

**決策**：`RouteAccessDecision` 僅允許 `checking`、`allow-management`、`allow-volunteer`、`redirect-login`、`redirect-volunteer`、`context-required`、`error`。Redirecting state 不掛載 children；`router.replace` 只在 destination 與目前 pathname 不同時執行。reload 與 browser back 都重新從 `checking` 開始。

**理由**：

- 有限 state 能以純函式 matrix 測試所有角色與錯誤分支。
- `replace` 可避免登入後或被拒管理 deep link 長期留在 history 中，back 仍會重新經過 boundary。
- context 缺少與暫時錯誤採終止畫面，而不是在 `/login`、`/`、`/animal-confirmation` 間自動來回。

**考慮過的替代方案**：

- **任何錯誤都直接前往 `/login`**：不採用；暫時錯誤或 context 缺少不等於 Session 失效，容易造成 loop 與不必要清除。
- **使用 `push` 保留每次 redirect**：不採用；browser back 容易反覆回到被拒的 management URL。

## 決策 8：不修改 OpenAPI、資料庫或後端授權

**決策**：本功能只新增 UI／route contract 與前端 composition。所有後端 endpoint、Pydantic schema、OpenAPI generated types、CRM model、Session、Membership、Active Context、Draft 與 management access checks 保持不變。

**理由**：

- 角色與單一 current draft 所需資訊已由既有 contract 提供。
- 前端 guard 是 UX 優化；直接呼叫管理 API 的志工仍由 `require_management_context` 與資料存取 scope 拒絕。
- 避免把 route UX 變更擴大成 authentication、CRM 或 LINE domain migration。

**考慮過的替代方案**：

- **新增專用 route-decision API**：不採用；profile/context 已足夠，會重複授權語意。
- **修改 JWT 加入可直接信任的 role/org claims**：不採用；既有設計要求每個 request 重新驗證 server-side Session 與 scope。

## 已解決的未知事項

- Route guard 執行位置：client boundary，先判斷再掛載 children。
- Role source：登入時使用 selected organization role；reload/deep link 使用 profile + Active Context。
- Root route：移入 `(management)` route group。
- 志工 route：必須驗證 Session／Context；不新增管理角色反向封鎖。
- Draft 策略：P0 單一 current draft，明確選擇後恢復；多筆留在 P1。
- API／資料：不新增 endpoint、schema、table 或正式前端資料副本。
- 驗證：Vitest decision matrix + Playwright route/network/back/reload + axe／responsive／visual + 既有後端 security/isolation regression。

本研究沒有未解決的設計問題。
