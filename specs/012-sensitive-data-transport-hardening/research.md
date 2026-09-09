# Research: 敏感資料傳輸與紀錄防護

## 現況摘要

### 已存在的良好控制

- FastAPI Uvicorn access logger 已對 `token`、`password`、`authorization`、LINE identity 與 provider credential 做值遮罩。
- public animal photo capability route 在 local／GCP nginx 使用不含 query 與 Referer 的專用 log format。
- LIFF volunteer entry 會移除 legacy `id_token`；animal confirmation 讀取 QR payload 後會清除 location query。
- photo capability 已綁定 purpose、organization、animal、object key 與 expiry，並有跨租戶／跨用途測試。
- staff signed-download 經 authenticated API 產生，物件存取仍有 organization scope。

### 已確認的缺口

- `apps/web/app/login/page.tsx` 的 `<form>` 未宣告 method，只靠 hydration 後的 `preventDefault()`；pre-hydration 原生提交預設為 GET，且 `username`／`password` 有 `name`，因此會形成含 credential 的 URL。
- 登入頁預填固定 `local-only-password`；當 Next.js 經 ngrok 公開時，`local-only` 的威脅假設不再成立。
- local 與 GCP nginx 的 standard format 記錄完整 `$request` 與 `$http_referer`；除 photo capability 外，敏感 query 會被保存。
- `test_line_local.sh` 的單一 public origin 目前以 catch-all 將 `/` 與 `/v1/` 全部轉送，因此管理登入與管理 API 一併暴露。
- FastAPI 的集中遮罩目前明確套用 Uvicorn access logger；多個 application module 直接使用 `logging.getLogger`，沒有證據證明所有 handler 都套用同一 filter。
- Next proxy 會原樣轉送 query；Next development log 與 ngrok inspector 不受 FastAPI filter 保護。
- `entry`、`qr_token`、staff signed URL 與 CLI raw entry reference 都是 credential-like 資料，但沒有單一例外清單統一說明 lifetime、scope、log 與清除政策。

## Decision 1：源頭禁止優先，log redaction 作第二道防線

**Decision**：Password、session token、LINE ID token 與長效 secret 不得被建成 URL。表單在 JavaScript 未掛載時也必須 fail closed；legacy URL 只做清理，不採信內容。各 log layer 仍需遮罩，以處理歷史連結、攻擊流量與第三方 callback。

**Rationale**：ngrok、瀏覽器歷史與上游 edge 在應用程式執行前就可能看見 URL；事後 `history.replaceState` 或 FastAPI filter 無法回收已保存副本。

**Alternatives considered**：只在 FastAPI redaction；只在頁面 mount 後清 query；將 HTTPS 視為足夠。三者都無法避免端點與中介系統保存 URL。

## Decision 2：登入採雙層防護

**Decision**：登入表單明確宣告非 GET 的原生語意，並在 hydration 前禁止可用提交；React 掛載後仍沿用既有 JSON POST。Password 不預填，測試自行輸入 synthetic credential。

**Rationale**：`preventDefault()` 只在事件 handler 已掛載時有效；明確 method 與 hydration guard 可分別處理 native fallback 與互動時序。

**Alternatives considered**：只移除 input `name` 會降低 password-manager／表單語意且未處理其他欄位；只加 `method=post` 雖不洩漏 URL，但 no-JS 時仍會把 credential POST 到不支援的頁面 route；兩層合併較清楚。

## Decision 3：URL 值分 A/B/C/D 四類，不全面禁止 query

**Decision**：分類為 Class A forbidden URL secret、Class B restricted URL capability、Class C public identifier、Class D ordinary query。Workflow locator 是 Class B 的 purpose 子型別；只有 Class B 在符合例外登錄時可攜帶授權能力，Class C/D 不得被 server 當成授權證明。

**Rationale**：搜尋、分頁與 cache version 是正常 URL 語意；LINE 圖片與 QR 也有客戶端／平台要求。全面移除 query 會破壞功能，全面允許 token 則會擴大外洩。

**Alternatives considered**：以參數名稱是否包含 `token` 判斷；只依 route 判斷。名稱不足以表達 purpose，route 也可能同時有敏感與一般 query。

## Decision 4：受控 URL 例外採 registry 與 fail-closed review

**Decision**：建立機器可讀的例外 registry，至少記錄 key／route、class、purpose、issuer、consumer、max lifetime、organization／resource binding、single-use／revocation、scrub timing、log policy、owner 與 tests。

**Rationale**：目前 photo capability 控制成熟，但 `entry`、`qr_token`、callback 與 signed URL 分散在不同模組。集中登錄能讓 CI 判斷新增例外是否完整，而不把業務授權搬進共用工具。

**Alternatives considered**：建立通用 token service；拒絕，因不同 token 的 purpose、client 與 revocation 語意不同，容易造成授權錯配。

## Decision 5：各 logging layer 使用共同結果、各自 enforcement

**Decision**：敏感 route 使用 query-free／Referer-free access format；結構化應用記錄使用 key/value mask；錯誤與 exception 使用相同 handler filter；Next 與 scripts 不輸出 raw credential。保留 method、path、status、size、latency、event name 與不可逆 correlation。

**Rationale**：nginx、Next、Uvicorn 與 application logger 的能力不同；硬做一個跨 runtime logger 會擴大架構。共同 policy 加各層最小 hook 能降低風險。

**Alternatives considered**：所有 request 一律不記 query；會降低一般搜尋與除錯能力，與既有「ordinary query retains logging」契約衝突。

## Decision 6：公開 LINE demo 採 route allowlist

**Decision**：預設 tunnel 僅公開 health（如必要）、LINE webhook、public media capability、LIFF entry／application／confirmation／care-report 必要頁面與對應 API／static assets；拒絕 `/login`、management pages 與 management API。遠端管理展示另以明確 opt-in 模式處理。

**Rationale**：目前 catch-all 單一 origin 是實際暴露管理入口的原因。單一 origin 可保留，但 edge routing 必須最小化。

**Alternatives considered**：依賴固定 demo password；依賴 URL 不公開；再開第二條 tunnel。前兩者不是 access control，後者增加 CORS 與操作複雜度且非必要。

## Decision 7：既有 capability 不在本功能猜測 TTL

**Decision**：保留現有 photo 300 秒與 staff signed URL 300 秒等 lifetime，先登錄實證與風險；若 runtime evidence 顯示不適用，另立變更。

**Rationale**：延長安全 lifetime 是權限設計變更，不能因 log hardening 順手修改。

**Alternatives considered**：統一所有 token TTL；不同用途無共同安全基準。

## Decision 8：一次性 URL 清理依流程階段執行

**Decision**：禁止 secret 立即移除且不採信；workflow locator 在完成 exchange／解析後清除；callback 僅保留完成協定所需欄位；retry 必要狀態改用不含秘密的 recovery marker 或 server-side state。

**Rationale**：立即清掉 `entry` 可能破壞 LIFF redirect／recovery；永久保留又增加 history、Referer 與 screenshot 風險。

**Alternatives considered**：所有 query 在首次 render 清除；不符合 LIFF recovery 流程。

## Decision 9：以 sentinel matrix 驗證跨層結果

**Decision**：測試生成不具真實權限的唯一 sentinel，執行 login、LIFF、QR、photo、signed URL、error 與 cross-tenant replay，再掃 browser URL/history、network target、nginx、Next、Uvicorn、application log 與 test artifact。

**Rationale**：static scan 能發現明顯 URL builder，無法證明 framework、proxy 與第三方 runtime 的實際行為。

**Alternatives considered**：只做 source grep；只做單元測試。兩者都不能覆蓋完整 request chain。

## Decision 10：本階段不重建 authentication/session 架構

**Decision**：登入 API、JWT／refresh token、sessionStorage、RLS 與角色模型保持不變。若後續要改 HttpOnly cookie、OAuth provider 或全面 CSP，另立規格。

**Rationale**：本次問題是 credential transport 與 exposure surface；混入 session redesign 會放大回歸面並延後 P1 封堵。

**Alternatives considered**：藉此全面改 cookie auth；安全上可能有價值，但不是修復 password-in-URL 的必要條件。
