# 功能規格：志工角色導向入口與管理路由隔離

**功能分支**：`004-volunteer-entry-route-isolation`

**建立日期**：2026-08-14

**狀態**：草稿

**輸入**：使用者描述：建立角色導向的登入後入口，讓志工進入志工回報流程，並隔離管理首頁與管理路由。

## 功能概述

StrayHub 的正式志工日常回報主要透過一個平台共用的 LINE Official Account、LINE Bot 與 LIFF 完成，使用 Rich Menu、Quick Reply、Postback、文字與照片輸入。每個收容所提供自己的 LIFF URL／QR Code，但共用同一個 LINE channel、Webhook 與 LIFF App；入口只表示志工希望協助的收容所，後端仍必須驗證 LINE 身分、有效 Membership 與 Active Shelter Context。LIFF／Next.js 志工頁面負責無感驗證後的回報入口、QR Code 或收容編號找動物、動物身分確認、草稿恢復、完整答案修改與長文字輸入。

正式志工從收容所專屬 LIFF／Rich Menu 入口進入時，不輸入 StrayHub 帳號密碼；擴充後的 LIFF exchange 在背景驗證 LINE 身分與收容所 entry reference，後端確認該志工可協助入口所指定的收容所後建立 Active Shelter Context，接著直接顯示該收容所今日可回報的狗狗。local Web／LIFF 帳號只保留作開發、自動化與故障診斷 fixture。目前 local fixture 登入後仍會進入 `/` 管理首頁，可能讓志工看到錯誤入口。本功能同時建立正式 LIFF 無感入口、local fixture 的角色導向，以及管理路由隔離；工作人員、收容所管理者與平台管理員維持既有管理工作台入口。

本功能調整正式 LIFF／local fixture 入口、路由可見性與使用者可理解的導回行為，並對既有 LIFF exchange request 做一項最小 contract 擴充：加入收容所 entry reference，由後端原子驗證 LINE Binding、限時 Membership 並建立 Session 與 Active Shelter Context。除此之外不改變 LINE Bot 主要回報流程、Webhook、CRM 資料模型、其他既有後端 API 契約、後端授權或租戶隔離規則。前端導回與 entry reference 只改善 UX，不是安全邊界。

## Clarifications

### Session 2026-08-14

- Q: 平台管理員切換 Active Shelter Context 失敗時，應如何處理仍有效的舊 context？ → A: 保留舊 context 與舊資料，顯示錯誤並允許重試。
- Q: 是否確認 P0 採用「共用 LINE Official Account／LIFF，加上收容所專屬入口 URL」？ → A: 確認採用共用 LINE／LIFF；正式志工由 LINE 無感驗證，收容所專屬入口建立經後端驗證的 Active Shelter Context。
- Q: 志工報名、管理員批次核准與預設 7 天限時授權，應納入目前入口隔離規格，還是拆成先完成的獨立 P0 功能？ → A: Membership lifecycle拆成獨立且先完成的P0規格；本功能只讀取其Application／Membership／Grant狀態，不在exchange中建立或變更授權。
- Q: 本入口規格是否允許小幅擴充 LIFF exchange contract，讓前端同時提交收容所 entry reference，由後端驗證限時 Membership 後原子建立 Session 與 Active Shelter Context？ → A: 允許擴充；entry reference 不授權，後端必須原子驗證並建立 Session/context。
- Q: 正式志工在 LIFF 操作中 Session 失效，但 LINE 身分仍可重新驗證時，系統應如何恢復？ → A: 每次失效事件自動重新執行一次 LIFF exchange；失敗後停止自動重試，顯示重新進入與回到 LINE 操作。
- Q: LIFF exchange 如何表達尚未報名、審核中與既有權限不可用？ → A: LINE token與entry均驗證成功後，以200回NEW／PENDING／ACTIVE／SUSPENDED；只有ACTIVE建立並回傳internal Session credential。無效token維持401，無效／撤銷／過期entry維持safe 403。

## 角色與入口邊界

- **志工**：LINE Bot 是主要日常回報入口；每個收容所提供自己的 LIFF URL／QR Code，但平台共用同一個 LINE Official Account、Messaging API channel、Webhook 與 LIFF App。志工由 LINE 無感驗證，不輸入 StrayHub 帳號密碼；入口指定的收容所通過 Membership 驗證後成為 Active Shelter Context，接著進入 `/animal-confirmation` 選擇今日照顧過的狗狗。LIFF／Web route 也負責草稿恢復、完整答案修改、長文字輸入與 Bot 中斷時的備援。
- **工作人員**：登入後進入既有管理首頁 `/`，可依既有授權使用管理工作台。
- **收容所管理者**：登入後進入既有管理首頁 `/`，可依既有授權使用管理工作台與收容所範圍內的管理功能。
- **平台管理員**：登入後進入既有管理首頁 `/`；若需要選擇 Active Shelter Context，必須先完成既有的 context 驗證，再使用管理工作台。

`local-volunteer-a`、`local-volunteer-b`、`local-staff-a` 與 `local-platform-admin` 只代表 local Web／LIFF 的測試 fixture。它們用來驗證角色、收容所入口與租戶邊界，不代表真正的 LINE 身分；正式志工流程仍必須以受控 LINE／LIFF 環境驗證。收容所 code、URL path、query 或 QR Code 不是授權憑證，也不得取代後端 LINE 身分、Membership 與 Active Shelter Context 驗證。

## P0／P1 範圍決策

### P0 範圍

1. 平台 MUST 共用一個 LINE Official Account、Messaging API channel、Webhook 與 LIFF App；每個收容所提供專屬 LIFF URL／QR Code，不為一般收容所建立獨立 LINE 基礎設施。
2. 志工報名、管理員批次核准／拒絕、預設 7 天且可調整的授權期限、到期／撤銷與 Audit Log 由獨立且先完成的 P0「志工報名與限時授權」規格負責；本功能不建立、核准、延長或撤銷 Membership。
3. 正式志工從收容所專屬入口進入後，由擴充後的 LIFF exchange 接收 LINE id token 與收容所 entry reference；後端 MUST 區分 NEW、PENDING、ACTIVE、SUSPENDED。只有 exact organization 的 Membership 已核准、status 為 active、尚未到期且 Grant／收容所狀態有效時，才在同一交易建立 Session 與 Active Shelter Context；其餘 state 不得留下部分 Session/context，志工也不輸入 StrayHub 帳號密碼。
4. 收容所專屬入口指定的 organization 只是請求的目標 context，不授予權限；驗證通過後，頁面 MUST 清楚顯示目前協助的收容所，並只載入該 context 今日可回報的狗狗、草稿與回報資料。
5. 志工在有效 context 下的預設入口為 `/animal-confirmation`，直接選擇今日照顧過的狗狗，不進入管理首頁，也不先執行管理 Dashboard 查詢。LINE Bot 在 context 已由專屬入口或既有對話狀態確認時，也先提供該收容所可回報狗狗的選擇。
6. 若 context 驗證完成後存在一筆可恢復的 active draft，志工先在志工入口看到恢復選擇；選擇繼續後進入 `/care-report`，選擇稍後處理則留在 `/animal-confirmation`。沒有可恢復草稿時直接使用動物確認流程。
7. 志工不得看到管理首頁、管理導覽、管理 Breadcrumb、管理 metrics、管理資料或管理 permission denied 畫面。
8. 志工直接開啟管理路由或管理 deep link 時，不顯示管理內容、資料、筆數或管理操作，並導回 `/animal-confirmation` 或顯示同等安全且可理解的志工入口。預設行為為導回 `/animal-confirmation`。
9. 管理路由隔離至少涵蓋 `/`、`/animals`、`/animals/[animalId]`、`/animals/[animalId]/timeline`、`/reports`、`/reports/[reportId]`、`/ai-review`、`/settings/*` 與 `/shelters`。
10. `/animal-confirmation` 保留今日名單、QR Code、收容編號搜尋與動物身分確認；`/care-report` 保留草稿恢復、回報填寫、保存與重試。
11. 深連結、重新整理、瀏覽器返回與 session 失效都必須重新遵守角色、Membership 有效期限與 Active Shelter Context 檢查；正式 LIFF Session 失效且 LINE 身分仍可驗證時，每次失效事件只自動重新執行一次 LIFF exchange，成功後回到原收容所流程，失敗後停止自動重試並顯示「重新進入」與「回到 LINE」。local 管理／測試 Session 失效時導向 `/login`。
12. local Web 帳號只作開發與自動化 fixture；其角色導向與租戶隔離 MUST 與正式 LIFF 流程一致，但帳密表單不是正式志工操作步驟。
13. 工作人員、收容所管理者與平台管理員維持既有 `/` 管理首頁入口、管理導覽與 Active Shelter Context 行為。
14. 前端 route、收容所 URL 與 Rich Menu 行為不得取代後端 API 授權、Membership 期限、CRM 唯一事實來源、原始回報保存、AI 人工覆核邊界或 Organization／Active Shelter Context 隔離。

### P1 範圍

P1 可在 P0 完成後獨立加入，但不得成為 P0 的必要依賴：

- 為特定收容所建立獨立 LINE Official Account、Messaging API channel、Webhook 或 LIFF App 的例外營運模式。
- 大規模 Rich Menu 分眾、收容所品牌客製、進階成效分析與多版本發布策略。
- 若未來調整既有「每位志工、每個 Active Shelter Context 最多一筆 active draft」規則，多筆 active draft 的恢復提示與選擇體驗。
- 不同裝置或多個 Active Shelter Context 的進階入口策略。

## 使用者情境與驗收（必填）

### 使用者故事 1－志工登入後直接開始回報（優先級：P0）

志工從收容所專屬 LIFF／Rich Menu 入口進入後，由 LINE 無感驗證身分與該收容所 Membership，在有效 Active Shelter Context 下直接進入動物確認流程，不輸入帳號密碼，也不需要先穿越管理工作台。local Web 登入只用於測試同一入口規則。

**為何是此優先級**：這是志工完成日常回報的第一步；移除錯誤入口可直接降低現場操作摩擦，且是其餘志工 route guard 的前提。

**獨立驗收**：使用同一個受控 LIFF App 的 ORG-A／ORG-B 專屬入口，分別以具有對應 Membership 的 LINE 測試身分進入，確認無帳密步驟、目前收容所正確、只顯示該收容所今日可回報狗狗，且沒有管理首頁內容或管理 Dashboard 查詢；再以 `local-volunteer-a` 與 `local-volunteer-b` fixture 重跑同一矩陣。

**驗收情境**：

1. **Given** 志工從某收容所專屬 LIFF／Rich Menu 入口進入且具備該收容所有效 Membership，**When** LINE 身分交換與 Active Shelter Context 建立完成，**Then** 不要求輸入帳號密碼，直接導向 `/animal-confirmation` 並顯示目前協助的收容所。
2. **Given** 志工從 ORG-A 專屬入口進入，**When** 後端驗證 LINE 身分與 Membership，**Then** 只顯示 ORG-A 今日可回報的狗狗、草稿與回報資料；把同一入口 URL 轉傳給未授權使用者不得授予 ORG-A 存取權。
3. **Given** 志工已進入 `/animal-confirmation`，**When** 使用者以今日名單、QR Code 或收容編號搜尋動物，**Then** 可以完成動物身分確認，不需要經過管理首頁。
4. **Given** 志工嘗試在 context 驗證完成前進入受保護志工流程，**When** 驗證尚未完成或失敗，**Then** 不顯示任何收容所動物資料，並提供等待、返回、重新選擇或聯絡管理者的安全下一步。

### 使用者故事 2－志工安全恢復 active draft（優先級：P0）

志工有可恢復的 active draft 時，能在確認目前收容所與角色後清楚選擇繼續或稍後處理；系統不會自動恢復錯誤收容所或未選定的草稿。

**為何是此優先級**：草稿包含志工已輸入的原始內容，必須兼顧低摩擦、資料保留與租戶隔離。

**獨立驗收**：準備沒有草稿、單一可恢復草稿、草稿過期、context 不一致與保存失敗的 fixture，從志工登入或 `/animal-confirmation` 重新整理開始測試恢復選擇與回報內容保留。

**驗收情境**：

1. **Given** 志工已完成 context 驗證且沒有 active draft，**When** 開啟志工入口，**Then** 直接顯示動物確認流程，不出現誤導性的恢復提示。
2. **Given** 志工已完成 context 驗證且有一筆可恢復的 active draft，**When** 開啟志工入口，**Then** 顯示「繼續回報」與「稍後處理」的清楚選擇；選擇繼續才進入 `/care-report`。
3. **Given** 志工的 active draft 已過期、已提交或已取消，**When** 開啟志工入口，**Then** 不將該草稿顯示為可恢復，也不自動載入其內容。
4. **Given** active draft 與目前 Active Shelter Context 不一致，**When** 系統檢查可恢復草稿，**Then** 不顯示草稿內容、不載入其他收容所資料，並說明需要切換或聯絡管理者的下一步。
5. **Given** 志工在 `/care-report` 保存失敗或 session 中斷，**When** 重新進入志工入口，**Then** 原始輸入仍可依既有規則恢復或重試，不被導向管理頁面。

### 使用者故事 3－志工直接開啟管理網址時不會看到管理資料（優先級：P0）

志工即使從書籤、瀏覽器歷史或外部訊息直接開啟管理 deep link，也只會看到安全的志工入口或角色限制訊息，不會短暫看到管理資料。

**為何是此優先級**：僅調整登入後入口不足以處理 deep link、返回與重新整理；管理內容不得在前端判斷角色前先被顯示或查詢。

**獨立驗收**：以志工 fixture 逐一開啟所有 P0 管理路由與帶有查詢參數的 deep link，觀察首次可見畫面、網路請求結果、導回位置與瀏覽器返回行為。

**驗收情境**：

1. **Given** 使用者以志工角色登入，**When** 開啟 `/`，**Then** 導向 `/animal-confirmation`，不得顯示 Dashboard、管理 metrics 或 permission denied 管理畫面。
2. **Given** 使用者以志工角色，**When** 直接開啟 `/animals`、`/animals/[animalId]`、`/animals/[animalId]/timeline`、`/reports`、`/reports/[reportId]`、`/ai-review`、`/settings/*` 或 `/shelters`，**Then** 不得看到受保護管理內容、資料筆數或管理操作，並導回志工入口或顯示安全的角色限制訊息。
3. **Given** 志工直接貼上帶有動物、回報或設定識別資訊的管理 deep link，**When** 頁面開始載入，**Then** 首次可見狀態不包含管理資料，也不因網址內容洩漏資料存在性。
4. **Given** 志工已被導回志工入口，**When** 使用瀏覽器返回或重新整理，**Then** 角色與 context 檢查仍有效，不會繞過限制重新顯示管理頁。

### 使用者故事 4－工作人員登入後維持管理首頁（優先級：P0）

工作人員登入後仍能進入既有管理首頁，查看既有管理工作台與被授權的管理路由；角色導向志工入口不會改變工作人員的既有下一步。

**為何是此優先級**：角色隔離必須雙向成立，不能以修正志工入口為由破壞現有管理工作流。

**獨立驗收**：以 `local-staff-a` 完成登入、重新整理 `/`、開啟既有管理 route 並使用返回，確認管理首頁與既有導覽可用。

**驗收情境**：

1. **Given** 使用者以工作人員角色登入且有有效 Active Shelter Context，**When** 登入流程完成，**Then** 維持進入 `/` 管理首頁的既有行為。
2. **Given** 工作人員已登入，**When** 重新整理 `/` 或從管理 deep link 返回，**Then** 仍顯示既有管理 Shell 與被授權的管理內容，不被導向 `/animal-confirmation`。
3. **Given** 工作人員沒有某項管理權限，**When** 開啟該受保護管理 route，**Then** 沿用既有安全權限提示，不因此取得志工入口以外的資料，也不洩漏未授權資料。

### 使用者故事 5－管理者維持原本的管理流程與 context 選擇（優先級：P0）

收容所管理者與平台管理員登入後仍進入管理首頁；平台管理員需要選擇 Active Shelter Context 時，先完成既有驗證再進入管理內容。

**為何是此優先級**：平台與收容所管理是現有核心工作流，且 context 驗證是多收容所資料隔離的必要條件。

**獨立驗收**：以管理者 fixture 驗證單一與多個可用 context、重新整理、切換失敗與管理 deep link，確認角色與租戶邊界不回歸。

**驗收情境**：

1. **Given** 使用者以收容所管理者角色登入且有有效 Active Shelter Context，**When** 登入流程完成，**Then** 維持進入 `/` 管理首頁的既有行為。
2. **Given** 使用者以平台管理員角色登入且需要選擇 Active Shelter Context，**When** context 尚未驗證，**Then** 先完成既有 context 選擇與驗證，不顯示未選定收容所的管理資料；驗證成功後才進入 `/`。
3. **Given** 平台管理員切換 Active Shelter Context，**When** 切換成功或失敗，**Then** 成功時只顯示新 context 範圍內容；失敗時保留後端仍確認有效的舊 context 與舊資料、顯示錯誤並允許重試，不得顯示任何新 context 的部分資料。

### 使用者故事 6－共用 LINE／LIFF 與 local fixture 遵循一致的志工權限邊界（優先級：P0）

所有收容所共用同一個 LINE Official Account、Messaging API channel、Webhook 與 LIFF App，透過不同收容所入口 URL 建立候選 context；P0 同時以受控 LINE／LIFF 身分與 local fixture 驗證入口及路由隔離，兩者對管理頁隔離與 context 要求一致。

**為何是此優先級**：正式志工操作不能依賴帳密登入；P0 必須證明共用 LINE 基礎設施可以為不同收容所建立隔離 context，且 local fixture 不會形成與真實通道不同的安全假設。

**獨立驗收**：使用同一 LIFF ID 的 ORG-A／ORG-B 專屬入口，以有權限、無權限及跨收容所 LINE 測試身分驗證 context、狗狗清單、草稿與管理 route matrix，再以 local volunteer fixture 重跑相同角色邊界。

**驗收情境**：

1. **Given** 志工由收容所專屬 LIFF URL 進入，**When** LINE／LIFF exchange 與 Membership 驗證成功，**Then** 使用共用 LINE channel 建立該收容所 Active Shelter Context，直接進入 `/animal-confirmation`。
2. **Given** 使用者由 local Web／LIFF fixture 以志工角色建立等價 Session，**When** 完成入口流程，**Then** 遵循與正式 LINE 相同的志工入口、草稿恢復與管理 route guard。
3. **Given** 志工對入口指定收容所的報名仍為 pending、已被拒絕、Membership 已撤銷或期限已到，**When** 完成 LINE 身分驗證，**Then** 不建立該 Active Shelter Context、不顯示狗狗或草稿，並說明等待核准、重新報名或聯絡管理者的安全下一步；本功能不得自行核准或延長授權。
4. **Given** 同一志工可協助多個收容所，**When** 從其中一個收容所專屬入口進入，**Then** 該入口只指定本次候選 context，後端仍重新驗證 Membership，且頁面清楚顯示目前協助的收容所。

### 使用者故事 7－遇到 session、context 或權限問題時知道下一步（優先級：P0）

使用者遇到 session 失效、沒有 Active Shelter Context、context 被撤銷、角色不符或暫時載入失敗時，可以看到台灣繁體中文的安全說明與可執行下一步。

**為何是此優先級**：入口隔離涉及多個驗證狀態；沒有清楚的降級行為，使用者可能重試到 redirect loop，或誤以為資料消失。

**獨立驗收**：對登入、志工入口、管理首頁與管理 deep link 注入 session 失效、context 缺少、權限拒絕與暫時錯誤，確認每種狀態只導向可理解且不洩漏資料的下一步。

**驗收情境**：

1. **Given** local 測試或管理使用者的 Session 已失效，**When** 開啟任一受保護 route，**Then** 導向 `/login`，不得保留可繼續查看的受保護內容。
2. **Given** 正式志工在 LIFF 中的 Session 失效但 LINE 身分仍可驗證，**When** 受保護 request 回覆 401，**Then** 系統以原收容所 entry reference 自動重做一次 LIFF exchange；成功後重新驗證並返回原收容所流程，失敗後不得再次自動重試，只顯示重新進入或回到 LINE。
3. **Given** 志工沒有有效 Active Shelter Context，**When** 嘗試進入志工回報流程，**Then** 不顯示其他收容所資料，並提供安全的 context 選擇、返回或聯絡管理者下一步。
4. **Given** 任何角色的入口檢查遇到暫時錯誤，**When** 系統顯示狀態，**Then** 使用台灣繁體中文說明目前狀態與重試、返回或重新登入方式，且不形成 redirect loop。
5. **Given** 使用者使用鍵盤或螢幕閱讀器，**When** 入口檢查、導回或權限狀態發生，**Then** loading、status、error 與主要下一步可被正確讀取，且瀏覽器返回不能繞過限制。

### Edge Cases

- 角色與 Active Shelter Context 尚在驗證時，頁面不得先顯示管理 Shell、管理 metrics、管理筆數或管理內容；等待狀態要說明正在確認入口。
- 登入回應沒有可用 Membership、Membership 已停用或平台管理員尚未選定 context 時，不能以預設收容所或前一次 session 的 context 代替明確驗證。
- 志工報名尚未核准、已拒絕、Membership 被撤銷或有效期限屆滿時，不得建立或沿用 Active Shelter Context；已保存的草稿與歷史資料不得刪除，但在重新取得授權前不可讀取或繼續提交。
- 志工的 active draft 已過期、已提交、被封存、跨收容所或動物已不可回報時，不得載入其內容；應說明可恢復性與下一步。
- 入口 route 具備 query string、尾端斜線、巢狀 `/settings/*` 或未知管理子路由時，仍不得因路徑變形繞過管理隔離。
- Session 在志工入口、草稿恢復或管理頁載入期間失效時，應立即清除可繼續使用的受保護內容；local 測試或管理流程導向 `/login`，正式 LIFF 流程依單次自動 exchange 規則處理。
- 正式 LIFF Session 失效後的自動 exchange 每次失效事件最多一次；自動交換失敗、回覆相同 401 或無法取得 LINE 身分時，必須進入安全終止狀態，不得繼續自動 refresh／exchange。
- 使用瀏覽器快取、返回、重新整理或重複點擊導覽時，不得造成志工與管理入口互相跳轉的 redirect loop。
- 管理使用者切換 Active Shelter Context 失敗時，必須保留後端仍確認有效的舊 context 與舊資料、顯示切換失敗提示並允許重試；不得把任何新 context 的部分資料與舊 context 內容混在同一畫面。
- 在約 360px 寬度、長中文提示、鍵盤操作與螢幕閱讀器情境下，loading、導回與權限提示不得被截斷、遮蔽或只用顏色表達。

## Requirements（必填）

### Functional Requirements

- **FR-001**：系統 MUST 在完成既有 LINE／LIFF 身分交換或 local fixture 登入後，依已驗證的角色與 Active Shelter Context 決定下一個入口；正式志工 LIFF 流程 MUST NOT 要求輸入 StrayHub 帳號密碼。
- **FR-002**：具備志工角色且有有效 Active Shelter Context 的使用者 MUST 以 `/animal-confirmation` 作為預設 Web／LIFF 入口，直接選擇目前收容所今日照顧過的狗狗，不得先進入管理首頁。
- **FR-003**：志工進入受保護回報流程前 MUST 完成 Session、角色、已核准且尚未到期的 active Membership、既有 LINE／LIFF 身分與 Active Shelter Context 驗證；收容所專屬 URL／QR Code 只指定候選 context，MUST NOT 授予權限。驗證未完成或失敗時 MUST 不顯示動物或管理資料。
- **FR-004**：若志工有一筆可恢復的 active draft，系統 MUST 在 context 驗證完成後提供繼續或稍後處理的選擇；只有狀態為 active 且尚未過期的草稿可被視為可恢復。
- **FR-005**：系統 MUST 拒絕恢復與目前 Active Shelter Context、志工授權範圍或 draft 狀態不一致的 draft，且不得揭露其內容、動物資料或存在性以外的受保護資訊。
- **FR-006**：`/animal-confirmation` MUST 保留今日可回報名單、QR Code、收容編號搜尋、動物身分確認與重新選擇等既有志工流程。
- **FR-007**：`/care-report` MUST 保留草稿恢復、完整答案修改、長文字輸入、保存、保存失敗保留原始輸入與重試等既有志工流程。
- **FR-008**：志工直接開啟 `/`、`/animals`、`/animals/[animalId]`、`/animals/[animalId]/timeline`、`/reports`、`/reports/[reportId]`、`/ai-review`、`/settings/*`、`/shelters` 或其管理 deep link 時，系統 MUST 在任何管理內容可見前導回 `/animal-confirmation` 或呈現同等安全的志工入口。
- **FR-009**：志工進入管理 route 時 MUST NOT 看到管理 Dashboard、管理導覽、管理 Breadcrumb、metrics、資料筆數、受保護資料或管理操作；前端不得先以管理查詢取得資料再顯示權限限制。
- **FR-010**：工作人員、收容所管理者與平台管理員 MUST 維持既有 `/` 管理首頁入口、管理導覽與已授權管理路由行為；平台管理員需要 context 時 MUST 先完成既有 context 驗證。Active Shelter Context 切換失敗時，系統 MUST 保留後端仍確認有效的舊 context 與舊資料、顯示錯誤並允許重試，且 MUST NOT 顯示任何新 context 的部分資料。
- **FR-011**：所有角色的 deep link、重新整理、瀏覽器返回與重複導覽 MUST 重新遵守角色、Session、Active Shelter Context 與租戶隔離規則，不得以瀏覽器歷史或 client state 繞過限制。
- **FR-012**：Session 失效時，系統 MUST 移除可繼續使用的登入狀態，並不得保留可繼續查看的受保護頁面內容；正式 LIFF 流程在每次失效事件 MUST 以原 entry reference 自動重新執行一次 LIFF exchange，成功後重新驗證並返回原收容所流程，失敗或再次收到 401 時 MUST 停止自動重試並顯示「重新進入」與「回到 LINE」。local 管理／測試流程 MUST 導向 `/login`。
- **FR-013**：沒有有效 Active Shelter Context、志工報名仍為 pending／已拒絕、Membership 被撤銷／已到期或 context 驗證失敗時，系統 MUST 不顯示任何收容所資料，並提供符合狀態的等待核准、重新報名、返回、重試或聯絡管理者下一步。
- **FR-014**：所有入口、loading、導回、錯誤、權限限制、草稿恢復與 context 狀態提示 MUST 使用台灣繁體中文，並在鍵盤、螢幕閱讀器與約 360px 手機寬度下可理解及操作。
- **FR-015**：角色導向 redirect 與 LIFF Session 自動 exchange MUST 不造成 loop；每次失效事件的自動 exchange 次數 MUST 不超過 1。入口檢查期間 MUST 提供可理解的 loading／status 狀態，且管理內容不得在檢查前短暫顯示。
- **FR-016**：除 FR-022 定義的 LIFF exchange request 最小擴充外，本功能 MUST 保持後端 API 授權、CRM 唯一事實來源、原始回報保存、AI 人工覆核邊界、LINE Bot 主要流程、Webhook、其他既有 API contract 與多收容所資料隔離行為不變。
- **FR-017**：local Web／LIFF fixture 與受控 LINE／LIFF 入口在角色、Active Shelter Context、草稿恢復與管理 route isolation 上 MUST 遵循同一套可觀察權限邊界；P0 MUST 在受控的共用 LINE channel／LIFF 環境驗證至少兩個收容所專屬入口與跨收容所拒絕情境。
- **FR-018**：所有一般收容所 MUST 共用同一個 LINE Official Account、Messaging API channel、Webhook 與 LIFF App；每個收容所 MUST 可取得自己的 LIFF URL／QR Code，且 P0 MUST NOT 要求為每個收容所建立獨立 LINE 基礎設施。
- **FR-019**：`/animal-confirmation` 與 `/care-report` MUST 清楚顯示目前 Active Shelter Context 的收容所名稱；動物、草稿、回報與保存操作 MUST 只使用後端確認的目前 context，切換或重新進入時不得顯示前一個收容所的 stale data。
- **FR-020**：LINE Bot 在 Active Shelter Context 已由收容所專屬入口或既有對話狀態確認時，MUST 先提供該收容所可回報狗狗的選擇；context 尚未確認時 MUST 先完成收容所驗證，不得以狗狗名稱、收容編號或 client state 推測租戶。
- **FR-021**：本功能 MUST 只讀取獨立 P0「志工報名與限時授權」功能提供的Application／Membership／Grant；MUST NOT 在 LIFF exchange、route boundary 或前端狀態中建立、核准、延長、撤銷或繞過 Membership。只有已核准、active且尚未到期的exact Membership／Grant可進入ACTIVE。
- **FR-022**：LIFF exchange request MUST 接收 LINE id token 與收容所 entry reference；後端 MUST 由 entry reference 解析候選 organization，並在單一交易中驗證 LINE identity、使用者、收容所及該 organization 的Application／Membership／Grant。有效identity與entry依狀態回NEW／PENDING／ACTIVE／SUSPENDED；只有ACTIVE能建立 Session 與 Active Shelter Context，其他state或任一失敗MUST不得留下部分狀態。

### Key Entities

- **已驗證 Session**：代表目前使用者可繼續使用受保護流程的登入狀態，包含角色與失效狀態；不得只以瀏覽器保存的 token 或 pathname 判定權限。
- **Active Shelter Context**：代表本次 Session 明確選定且由後端驗證的單一收容所範圍；所有志工 draft、動物確認與回報都必須與此範圍一致。
- **角色與入口決策**：由已驗證角色、Session 與 context 決定志工入口、管理首頁、context 選擇、登入頁或安全錯誤下一步的可觀察結果。
- **可恢復 active draft**：志工尚未完成的回報草稿，包含既有回報進度與原始輸入；只能在狀態、志工授權與 Active Shelter Context 均一致時提供恢復。
- **管理受保護路由**：需要工作人員、收容所管理者或平台管理員等既有管理權限的入口與頁面，包含管理首頁、動物、回報、AI、設定與收容所管理路由。
- **Local Web／LIFF role fixture**：用來驗證角色導向與租戶邊界的虛構測試帳號，不代表真實 LINE 身分或正式使用者資料。
- **收容所專屬入口**：共用 LIFF App 下帶有收容所識別的 URL／QR Code，用來提出本次希望進入的候選 Active Shelter Context；它不是授權憑證，必須搭配後端驗證的 LINE 身分與有效 Membership。
- **限時志工 Membership**：由獨立 P0 功能在收容所管理員核准報名後建立，預設有效 7 天且可由管理員調整；本功能只判斷其核准、active 與尚未到期結果，不管理其生命週期。

## 非功能需求

- **安全與隱私**：任何前端導回都不得被視為安全控制；後端仍必須拒絕未授權管理 API、跨收容所查詢與不一致的 Active Shelter Context。錯誤、空狀態與導回頁不得洩漏受保護資料是否存在、筆數或內容。
- **穩定性**：入口判斷不可產生 redirect loop；session、context 或 draft 檢查失敗時必須有終止狀態與可理解下一步。
- **可觀察體驗**：導回期間應顯示不洩漏資料的 loading／status；不得因角色判斷而短暫顯示管理資料或可操作控制。
- **可及性**：主要入口、導回、loading、錯誤、權限限制與草稿恢復選擇可用鍵盤與螢幕閱讀器完成；瀏覽器返回不得繞過角色限制。
- **響應式**：志工入口與安全狀態至少支援約 360px 手機寬度，長中文、錯誤訊息與主要操作不得重疊或截斷。
- **語言一致性**：使用者可見提示以台灣繁體中文為主；技術路徑、角色代碼與既有產品術語可保留英文。

## Success Criteria（成功標準）

### Measurable Outcomes

- **SC-001**：在 P0 受控 LINE／LIFF 與 local fixture 驗收中，100% 的正式志工從收容所專屬入口完成 LINE 無感驗證後，在有效 Active Shelter Context 下進入 `/animal-confirmation` 或明確的草稿恢復選擇，不輸入 StrayHub 帳號密碼，也不進入管理首頁。
- **SC-002**：在涵蓋所有 P0 管理路由、巢狀 `/settings/*`、query string、重新整理與瀏覽器返回的測試中，100% 的志工嘗試不得顯示管理資料、metrics、筆數或管理操作。
- **SC-003**：在既有工作人員、收容所管理者與平台管理員 fixture 的回歸測試中，100% 維持既有 `/` 管理首頁入口；需要 context 的平台管理員 100% 先完成 context 驗證。
- **SC-004**：在沒有草稿、單一草稿、草稿過期、context 不一致與草稿保存失敗的 P0 測試矩陣中，100% 的志工都能在不跨租戶的前提下得到繼續、稍後處理、重試、返回或聯絡管理者的明確下一步。
- **SC-005**：在入口檢查與管理 deep link 的測試中，100% 的初次可見狀態不包含管理資料，且不發出不必要的管理 Dashboard 查詢；所有角色 redirect 測試均不產生 redirect loop。
- **SC-006**：志工從登入或入口開始，在不經過管理首頁的情況下，可完成動物確認並建立或恢復照護回報流程；既有動物確認與 `/care-report` regression tests 100% 通過。
- **SC-007**：既有後端權限、Organization／Active Shelter Context 租戶隔離、API contract、CRM 原始保存、AI 人工覆核、LINE Bot 與 LIFF exchange regression tests 全部通過；本功能不得以收容所 URL、Rich Menu 或新增前端導回測試取代後端授權測試。
- **SC-008**：P0 可在約 360px 手機寬度，以受控 LINE／LIFF 環境完成至少 ORG-A／ORG-B 兩個專屬入口的身分驗證、狗狗選擇、跨收容所拒絕與回報入口驗收；local fixture 可獨立重跑相同矩陣，志工入口的鍵盤與螢幕閱讀器驗收均可完成。
- **SC-009**：P0 驗收中，所有一般收容所入口使用同一個 LINE Official Account、Messaging API channel、Webhook 與 LIFF App；兩個收容所專屬 URL 必須建立不同且正確的 Active Shelter Context，動物、草稿與回報資料交叉顯示率為 0%。
- **SC-010**：以 pending、rejected、revoked、expired 與 active-unexpired Membership fixture 驗收時，前四種狀態建立 Active Shelter Context、讀取狗狗／草稿或提交回報的成功率為 0%，只有 active-unexpired 狀態可進入回報流程；原有草稿與歷史資料不因授權到期而被刪除。
- **SC-011**：LIFF exchange contract tests 必須證明正確 entry reference 與 active-unexpired Membership 會同時建立 Session/context，而錯誤、跨收容所、pending、revoked、expired 或停用收容所案例建立 Session、context 或任何部分授權狀態的數量為 0。
- **SC-012**：正式 LIFF Session 失效矩陣中，每次失效事件的自動 exchange request 數不得超過 1；成功案例返回原收容所流程，失敗與重複 401 案例均終止於可操作的重新進入／回到 LINE 狀態，連續導向或 exchange loop 數為 0。

## Assumptions（假設）

- P0 使用一個平台共用的 LINE Official Account、Messaging API channel、Webhook 與 LIFF App，在受控環境驗證至少兩個收容所專屬入口；local Web／LIFF fixture 保留作自動化、開發與故障診斷，不是正式志工帳密流程。
- 獨立 P0「志工報名與限時授權」功能必須先提供報名、收容所管理員批次核准／拒絕、預設 7 天且可調整期限、到期／撤銷與 Audit Log；本功能開始實作正式入口前，該依賴必須已有可驗證 contract。
- LINE Bot 的主要對話流程與 Web／LIFF 輔助流程不是同一個 UI，但共用既有後端身分、授權、CRM 與租戶邊界。
- `local-volunteer-a`、`local-volunteer-b`、`local-staff-a` 與 `local-platform-admin` 只作為測試 fixture；規格不把它們描述成真正的 LINE 身分。
- 每個收容所專屬 LIFF URL／QR Code 使用可識別但不具授權能力的收容所 reference；URL 被轉傳時，後端仍以目前 LINE 身分與 Membership 決定是否可建立該 context。
- LIFF exchange 的最小 contract 擴充只新增收容所 entry reference；正式 authorization 仍由後端資料判定，request 不直接接受可被 client 任意指定的角色、Membership 狀態或期限。
- 志工從收容所專屬入口進入時不需要再次選擇收容所；若從共用 Rich Menu 的通用入口進入且同時具備多個有效 Membership，必須先明確選擇本次收容所，再載入狗狗或草稿。
- 志工進入管理 route 時，預設導回 `/animal-confirmation`；不另建立新的 403 管理頁作為 P0 必要範圍。
- active draft 的預設處理是「先驗證 context，再在志工入口提供恢復選擇」；志工明確選擇繼續後才進入 `/care-report`，以避免誤載入草稿或讓登入流程意外改變工作狀態。
- P0 沿用既有「每位志工、每個 Active Shelter Context 最多一筆 active draft」規則；多筆草稿策略屬於 P1，且只有在未來另行調整既有業務規則後才適用。
- 工作人員、收容所管理者與平台管理員的既有入口、導覽、Active Shelter Context 與後端授權契約是本功能的依賴，不在本功能重新定義。
- 所有受保護 route 都以既有 session 與後端驗證結果為準；網址、query string、sessionStorage、瀏覽器歷史與 client state 不是授權來源。

## Out of Scope（不在範圍內）

- 新增或修改 CRM 資料模型、角色模型、Membership、Active Shelter Context 或 active draft 的業務語意。
- 志工報名資料、管理員批次核准／拒絕 UI、Membership 的 7 天預設期限與調整、到期排程、撤銷及其 Audit Log；這些由獨立且先完成的 P0「志工報名與限時授權」規格負責。
- 新增志工業務功能、重做動物確認、照護回報表單或管理工作台視覺設計。
- 修改 LINE Bot Conversation State Machine、Webhook Signature、Event Idempotency 或既有後端授權原則；LIFF exchange 只允許 FR-022 的 entry reference 最小擴充，不得藉此改變 Membership 授權語意。
- 以任何前端 redirect、隱藏導覽或 UI 條件取代後端 API 權限控制與多收容所資料隔離。
- 為每個收容所建立獨立 LINE Official Account、Messaging API channel、Webhook、LIFF App 或各自維運的憑證；P0 採平台共用基礎設施。
- 收容所專屬 Rich Menu 視覺品牌、多版本分眾、進階成效分析與大規模 production rollout；P0 只要求共用 Rich Menu／專屬入口及受控環境驗證。
- 將正式志工改為 StrayHub 帳號密碼登入；帳密只保留給 local fixture、管理使用者或故障診斷。
- 重新設計管理首頁、管理 Sidebar、管理 Breadcrumb、Dashboard metrics 或管理頁面資訊架構。
- 建立新的 403 route、公開錯誤頁、跨收容所切換策略或多裝置同步策略作為 P0 必要功能。
- 改變 AI 摘要、人工覆核、原始回報保存、照片處理、CRM 唯一事實來源或 FR-022 以外的既有 API contract。
