# 研究：志工角色導向入口與管理路由隔離

**功能**：[spec.md](spec.md)

**研究日期**：2026-08-16

## 決策 1：正式入口由 LIFF SDK 取得 raw ID token

**決策**：收容所專屬 URL／QR Code 指向共用 LIFF App 的 `/volunteer-entry?entry=<opaque-reference>`。頁面每次開啟先執行 `liff.init({ liffId })`；外部瀏覽器若未登入，使用 LIFF login flow。初始化完成且已登入後，以 `liff.getIDToken()` 取得 raw ID token，連同 `entry` 送至後端。正式流程不接受 query string 傳入的 id token，也不把 `getDecodedIDToken()` 的 profile 當 server identity。

**理由**：LINE 官方文件要求每次開啟頁面初始化 LIFF，並明確區分 raw ID token（可送 server）與 decoded profile（只供 client 顯示）。ID token 只有在 LIFF App 啟用 `openid` scope 且使用者授權時可取得。參考 [LIFF API reference](https://developers.line.biz/en/reference/liff/) 與 [Developing a LIFF app](https://developers.line.biz/en/docs/liff/developing-liff-apps/)。

**考慮過的替代方案**：

- **把 id token 放在 shelter URL query**：不採用；token 會出現在歷史、log、分享連結與截圖，也無法代表當次 LIFF 初始化結果。
- **送 decoded ID token payload**：不採用；client 可修改，LINE 官方亦要求 server 使用 raw token。
- **為每個收容所建立 LIFF App**：不採用；FR-018 明定 P0 共用一個 LINE OA／channel／Webhook／LIFF App。

## 決策 2：entry reference 只解析候選 organization

**決策**：沿用005的`VolunteerEntryResolverPort`與digest-at-rest `ShelterEntryReference`。後端在LINE identity驗證後對raw reference計算digest，透過固定purpose、最小輸出的resolver取得安全organization公開context；resolver不得設定ambient organization scope。reference不包含user、role、Membership、期限或授權結果。

**理由**：入口 URL 必然可能被轉傳；把 reference 限制為 organization selector，才能保證同一 URL 對未授權 LINE identity 不產生存取權。005 已提供 rotation、revocation、cross-purpose 拒絕與 runtime 無跨租戶 SELECT 的 contract，004 不應建立第二套解析規則。

**考慮過的替代方案**：

- **URL 直接帶 organization UUID/code**：不採用；容易形成 client-controlled scope，且無法輪替或撤銷入口。
- **reference 自帶簽名與 Membership claim**：不採用；會建立第二個授權事實來源並可能在 Membership 撤銷後仍有效。
- **先查所有 Membership 再猜 organization**：不採用；多 Membership 使用者會產生歧義，也違反專屬入口語意。

## 決策 3：exchange 以 exact organization 的有效 Membership／Grant 原子建立 Session/context

**決策**：`POST /v1/auth/liff/exchange`在同一AsyncSession transaction依序完成：驗證LINE id token → resolve entry並鎖定Entry／Organization且不開啟ambient tenant scope → 鎖定active Binding → 設定exact user＋organization authentication scope → 鎖定並驗證User → 依全域固定Grant→Membership順序鎖定候選organization的實際Grant與`VOLUNTEER` Membership（與管理撤銷／expiration worker一致）→ 讀取exact Application → 回NEW、PENDING或SUSPENDED且不建立credential，或對ACTIVE套用005的`status=active && valid_from <= db_now < expires_at` predicate → 建立`SessionRecord(active_organization_id=organization_id)`與`RefreshTokenRecord` → 先驗證state-discriminated response再commit。任一resolver、資料庫、response validation、flush或commit失敗即rollback；非LINE identity錯誤統一為不洩漏內因的safe 503。

**理由**：Session 與 Active Shelter Context 實際由同一 `SessionRecord` 表示；把 context 一起寫入同一 row，可避免「有 Session、無 context」或反向部分狀態。鎖定 Membership/Grant 使 concurrent revoke/expire mutation 與 exchange 具備明確 commit 順序；commit 後的撤銷仍由 request-time predicate 與 005 cleanup 阻止後續存取。

**考慮過的替代方案**：

- **先 exchange 建 Session，再呼叫 context switch**：不採用；第二步失敗會留下可用 Session 或錯誤 context，違反 FR-022。
- **只檢查 Membership.role**：不採用；忽略 valid_from、expires_at、Grant、user/org status 與撤銷狀態。
- **由 client 再送 organization_id**：不採用；重複且可竄改，候選 organization 只能來自 resolver。

## 決策 4：LIFF exchange 不管理 Membership lifecycle

**決策**：exchange只讀取005的Application／Membership／Grant，不管理其lifecycle。沒有申請／Membership回NEW，pending回PENDING，既有但future、expired、revoked、disabled或缺少Grant回SUSPENDED；三者皆不建立session credential。只有有效exact Membership／Grant回ACTIVE。exchange不建立、修復、延長、重新啟用或撤銷任何access record；既有Draft／Report／Media不刪除。

**理由**：人工核准與限時授權是 005 的 CRM/Audit 邊界。若 exchange 自動修復或授權，會繞過管理員決定與期限治理。

**考慮過的替代方案**：

- **第一次 exchange 自動建立 VOLUNTEER Membership**：不採用；繞過核准。
- **expired 時自動延長 7 天**：不採用；繞過政策與 Audit。
- **失敗時刪除草稿**：不採用；授權失效不等於原始資料可刪除。

## 決策 5：正式 LIFF Session recovery 採 single-flight epoch

**決策**：volunteer layout 持有 `LiffRecoveryEpoch`。同一頁面在尚未進入 recovery 時遇到第一個 protected 401，建立唯一 in-flight Promise；同時到達的其他 401 共用該 Promise，不增加 exchange 次數。使用已初始化 LIFF 的新 raw ID token 與原 entry reference exchange 一次。成功後重新驗證 profile/context 並 reload/replace 回原 volunteer route；原 mutation 不自動重播。若 exchange 失敗、無法取得 token/reference，或恢復後再次 401，epoch 進入 terminal state，顯示「重新進入」與「回到 LINE」。

**理由**：頁面可能同時載入 animals、draft 與 profile；沒有 single-flight 會產生多次 exchange。禁止自動重播 mutation 可避免建立重複 Draft、回報或保存。有限 epoch 可直接證明每次失效事件 exchange 次數不超過 1 且沒有 loop。

**考慮過的替代方案**：

- **每個 `authFetch` 自行 refresh/exchange**：不採用；並行 401 會重複建立 Session。
- **無限重試直到成功**：不採用；可能形成 exchange/redirect loop。
- **自動重播所有 request**：不採用；非冪等 mutation 可能重做。

## 決策 6：entry reference 可作 transient recovery hint，但不是授權 cache

**決策**：正式 exchange 成功後，client 可在 sessionStorage 保存原 entry reference 與「LIFF session」來源標記，僅供同一 browser session 的一次 recovery。它不得保存 Membership status/expiry 或直接指定 Active Shelter Context；每次 recovery 後端仍完整 resolve 與驗證。logout、entry 變更、terminal cross-context/entry error 時清除。local credential fixture 不建立 LIFF recovery hint。

**理由**：FR-012 要求使用原 entry reference 自動 exchange；在導向 `/animal-confirmation` 後仍需可取得它。reference 本身不授權，短期 client 保存不改變 server security boundary。

**考慮過的替代方案**：

- **把 entry 永久留在所有 volunteer URL**：不採用；容易被複製到 deep link 並污染分析/log。
- **只放 React memory**：不採用；reload 後無法依規格恢復。
- **保存 role/expiry 避免 server call**：不採用；會使用 stale authorization。

## 決策 7：使用不掛載 children 的 client authenticated boundary

**決策**：access token 仍沿用 sessionStorage，因此 management 與 volunteer route group 共用 client boundary。Boundary 先取得 `/v1/auth/me` 與 `/v1/auth/active-shelter-context`，推導有效角色與 context；判定完成前只顯示安全 status，不掛載 page children。management role 通過後才取得 organizations 並掛載 Management Shell；volunteer route 通過後才取得 shelter label、animals、draft 或 care-report。

**理由**：Next middleware/Server Component 無法直接使用 sessionStorage token。client boundary 若不 render children，仍可阻止 child effect 與管理 request 在角色判斷前發生，且不需擴張成 cookie auth migration。

**考慮過的替代方案**：

- **Next middleware 依角色 redirect**：不採用；必須先遷移 auth storage，超出 004。
- **每個 page 自行 `useEffect` redirect**：不採用；會先掛載 children、重複查詢並可能 flash 管理資料。
- **只隱藏 Sidebar**：不採用；不能阻止 Dashboard/detail request。

## 決策 8：有效角色由 profile + Active Shelter Context 推導

**決策**：local login 在 context switch 成功後以 selected organization 的後端 role 決定目的地；deep link/reload/back 則由 `/auth/me` 的 platform role／Membership 與 `/auth/active-shelter-context` 的 organization 重新推導。`PLATFORM_ADMIN` 優先；其他角色必須有 matching active Membership。sessionStorage 的 organization id/code 只作 label cache。

**理由**：Membership 或 context 可在頁面間被撤銷、到期或切換，不能永久相信 login response。由 server response 組合可保持 direct URL 與 reload 一致。

**考慮過的替代方案**：

- **永久保存 role**：不採用；會 stale。
- **由 pathname 推測角色**：不採用；網址不是權限來源。
- **用 management API 的 403 猜角色**：不採用；會先發出不必要管理 request。

## 決策 9：`/` 與全部管理 route 共用 route-group gate

**決策**：將 root page 移到 `app/(management)/page.tsx`，`management-home.tsx` 只 render Dashboard content。`app/(management)/layout.tsx` 包住現有與未來全部管理 routes，包括 animals、reports、care calendar、AI review、settings、volunteers 與 shelters。角色未通過前不取得 organizations、Dashboard 或 page-specific data。

**理由**：route group 不改 URL；統一 gate 可涵蓋 dynamic route、query、尾端斜線與未來子路由，不需維護易漏的 pathname allowlist。

**考慮過的替代方案**：

- **在 root 保留第二個 guard**：不採用；形成兩套掛載順序與重複 profile/context request。
- **逐頁加 guard**：不採用；新 route 容易漏加。

## 決策 10：current draft 在 context gate 後以既有單一 contract 組合

**決策**：`/animal-confirmation` 在 volunteer boundary 通過後並行取得目前 context 的 shelter label、今日動物與 `/v1/line/care-report/drafts/current`。只有 active、未過期、同 context 且 animal 仍可回報時顯示「繼續回報／稍後處理」。繼續前往 `/care-report` 並由該頁重新讀 current draft；稍後只關閉本次提示，不修改 Draft。

**理由**：既有 domain 限制每位志工／context 最多一筆 active draft；不需要新 API 或資料模型。重新讀取可避免 prompt 到 navigation 間的 stale state。

**考慮過的替代方案**：

- **login 直接自動導向 draft**：不採用；可能在錯誤 context 載入內容，也剝奪志工選擇。
- **將完整 draft 放進 client route state**：不採用；易 stale 且擴大敏感資料生命週期。
- **P0 支援多筆草稿**：不採用；需另行修改 domain invariant。

## 決策 11：LINE Bot 維持既有狀態機，只增加 regression 證據

**決策**：不修改 Webhook signature、idempotency 或 Conversation State Machine。已由 entry/existing conversation 確認 organization 的 session 沿用現有 dog-first 選擇；沒有唯一有效 context 時沿用 `requires_liff`／選擇收容所流程。測試確保名稱、收容編號與 client state 不會推測 organization。

**理由**：FR-020 描述既有應維持的入口邊界，且 Out of Scope 明確排除重做 LINE Bot state machine。005 的有效 Membership predicate 已成為 session resolution 基礎。

**考慮過的替代方案**：

- **讓 Bot 直接解析 entry query**：不採用；Webhook event 沒有可信 browser context。
- **以狗狗名稱推測收容所**：不採用；跨收容所可能同名。

## 決策 12：local fixture 與受控 LINE／LIFF 分層驗收

**決策**：自動化使用 deterministic local LINE verifier、ORG-A/ORG-B entry reference 與 access-state matrix，證明 transaction、route、recovery、request ordering 與租戶隔離。P0 release gate 另使用一個共用受控 LINE OA/channel/Webhook/LIFF App、兩個 organization entry URL 與至少兩個測試 identity，驗證真實 `liff.init/getIDToken`、正確 context、跨收容所拒絕及 360px 流程。受控證據不含 raw token/reference 或個資。

**理由**：browser mock 無法證明 LINE SDK、channel audience 與真實 ID token verifier；真實 LIFF 驗收也不適合取代可重跑的 failure matrix。兩層證據共同滿足 FR-017 與 SC-008～SC-012。

**考慮過的替代方案**：

- **只做 Playwright mock**：不採用；無法證明共用 LIFF/channel integration。
- **所有 CI 使用真實 LINE account**：不採用；不穩定、需要個人互動與正式憑證。
- **每個 shelter 獨立 channel 測試**：不採用；與 P0 infrastructure 決策相反。

## 研究結論

- 正式身分：LIFF SDK 取得的 raw ID token，由後端既有 LINE verifier 驗證。
- 收容所判定：005 的 opaque entry reference 只解析候選 organization。
- 狀態判定：有效identity＋entry後依exact organization的Application／Membership／Grant回NEW／PENDING／ACTIVE／SUSPENDED；只有ACTIVE包含credential。
- 授權判定：exact organization 的 active、已開始、未到期 `VOLUNTEER` Membership + active Grant + active user/org。
- 原子邊界：Session、Refresh Token 與 Active Shelter Context 同 transaction commit；失敗部分狀態為 0。
- 前端邊界：children mount 前完成 profile/context/role gate；管理 request ordering 可觀察。
- 恢復邊界：每個失效 epoch 至多一次 exchange，mutation 不自動重播，terminal state 不 loop。
- 驗收邊界：local deterministic matrix + 共用受控 LINE／LIFF 雙層證據。

所有 Technical Context 的未知事項均已解決，沒有 `[NEEDS CLARIFICATION]`。
