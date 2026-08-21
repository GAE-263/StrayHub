# Controlled LINE／LIFF 驗收證據模板

本文件是Task 16建立的**受控真機驗收模板**。它定義如何從Next.js與FastAPI本機服務建立兩條HTTPS tunnel、設定LIFF Console、產生一次性entry reference，並以真實LINE帳號執行Case A–D。

Task 16只建立可執行的流程與遮罩後記錄格式；在沒有真實LIFF ID、LINE Login channel、受控帳號與手機操作結果前，不得把任何Case標記為通過。

## 1. 安全邊界

- 只使用受控測試LINE Official Account、LINE Login channel、Messaging API channel與虛構`ORG-A`／`ORG-B`資料。
- raw LINE ID token、raw entry reference、LINE user ID、個人姓名、電話、照片、動物 protected data與JWT不得貼入issue、PR、Git、terminal transcript、screenshot或本文件。
- raw entry reference只由發行script在stdout顯示一次；立即交給受控QR／URL測試流程，證據只保存reference ID的遮罩值或最後4碼。
- 所有實際結果必須記錄UTC時間、裝置／OS、app/channel設定版本、Case ID、HTTP status、可觀察畫面結果與遮罩後截圖路徑。
- 本文件中的`<...>`都是待受控環境替換的placeholder；placeholder不得出現在LIFF Console、Rich Menu或實際手機測試URL。

## 2. 服務與環境對照

| 邊界                   | 實際消費者                                          | Task 16設定                                   | 要求                                                                   |
| ---------------------- | --------------------------------------------------- | --------------------------------------------- | ---------------------------------------------------------------------- |
| Web tunnel             | 手機LINE開啟LIFF Endpoint、Next.js                  | `PUBLIC_WEB_ORIGIN`                           | HTTPS；轉發`127.0.0.1:3001`                                            |
| API tunnel             | Next.js `/v1/[...path]` server proxy                | `API_BASE_URL`                                | HTTPS；轉發`127.0.0.1:8001`；不可是localhost或空值                     |
| LIFF runtime           | `apps/web/app/(volunteer)/volunteer-entry/page.tsx` | `LIFF_ID`                                     | 使用LIFF Console中與LINE Login channel綁定的LIFF ID；Next.js啟動時讀取 |
| Rich Menu base         | `scripts/sync_line_rich_menu.py`                    | `LIFF_BASE_URL`                               | 必須是`https://liff.line.me/<LIFF_ID>`，不可帶path、query或fragment    |
| Rich Menu entry        | `infra/gcp-demo/line-rich-menu.yaml`                | `SHELTER_ENTRY_REFERENCE`                     | 只在受控shell handoff提供一次；產生`/volunteer-entry?entry=...`        |
| LINE identity verifier | FastAPI runtime                                     | `LINE_LOGIN_CHANNEL_ID`與對應Secret reference | 必須與LIFF App所屬LINE Login channel一致；不把Secret寫入本文件         |

`NEXT_PUBLIC_LIFF_ID`與`NEXT_PUBLIC_API_BASE_URL`不是目前volunteer entry runtime的source of truth；不要用它們取代server runtime的`LIFF_ID`與`API_BASE_URL`。

## 3. 啟動本機服務與兩條HTTPS tunnel

### 3.1 啟動local stack

```bash
cp .env.example .env

docker compose -f infra/local/docker-compose.yml up -d postgres minio
$HOME/.local/bin/uv run alembic upgrade head
$HOME/.local/bin/uv run python -m scripts.seed_local
```

分別啟動API與Next.js。`API_BASE_URL`與`LIFF_ID`在Next.js啟動前就必須設定，因為兩者由server runtime讀取：

```bash
$HOME/.local/bin/uv run python -m uvicorn services.api.app.main:app \
  --reload --host 127.0.0.1 --port 8001

API_BASE_URL="<PUBLIC_API_ORIGIN>" \
LIFF_ID="<LIFF_ID_FROM_CONSOLE>" \
npm --prefix apps/web run dev -- --hostname 127.0.0.1 --port 3001
```

### 3.2 建立兩條public HTTPS tunnel

以`cloudflared`為例，分別開兩個terminal：

```bash
cloudflared tunnel --url http://127.0.0.1:3001
cloudflared tunnel --url http://127.0.0.1:8001
```

若受控環境使用ngrok，對應指令為：

```bash
ngrok http 3001
ngrok http 8001
```

從兩個tunnel工具取得不同的HTTPS origin後，填入受控shell（以下只示意格式，不可原樣使用）：

```bash
export PUBLIC_WEB_ORIGIN="https://<web-tunnel-host>"
export PUBLIC_API_ORIGIN="https://<api-tunnel-host>"
export LIFF_ID="<LIFF-ID-FROM-CONSOLE>"
export LIFF_BASE_URL="https://liff.line.me/${LIFF_ID}"
```

確認：

```bash
curl --fail --silent "${PUBLIC_API_ORIGIN}/healthz"
curl --fail --silent --head "${PUBLIC_WEB_ORIGIN}/volunteer-entry"
```

若更換`API_BASE_URL`或`LIFF_ID`，必須停止並重新啟動Next.js；不要期待已啟動的server process重新讀取shell變數。

## 4. LIFF Console設定

在與`LINE_LOGIN_CHANNEL_ID`相同的LINE Login channel中設定受控LIFF App：

1. Endpoint URL設為`${PUBLIC_WEB_ORIGIN}/volunteer-entry`。
2. 啟用`openid` scope；不要以本機`localhost`、fake LIFF ID或HTTP URL作為正式受控測試設定。
3. 確認LIFF App所屬channel與後端`LINE_LOGIN_CHANNEL_ID`的audience設定一致。
4. 將設定版本、LIFF App非敏感識別與Endpoint hostname記錄在證據表；不要記錄channel secret、access token或raw LIFF ID token。
5. 手機LINE開啟的是LIFF App／Rich Menu URL，不是直接把raw entry reference貼到一般瀏覽器或issue。

Rich Menu的URI必須由`https://liff.line.me/<LIFF_ID>/volunteer-entry?entry=<opaque-reference>`產生；不得使用Web tunnel origin直接取代`LIFF_BASE_URL`。

## 5. 發行entry reference與Rich Menu dry-run

先以organization UUID發行受控reference。script的正確入口需要`PYTHONPATH=.`，且raw reference只在stdout出現一次：

```bash
PYTHONPATH=. $HOME/.local/bin/uv run python \
  scripts/issue_volunteer_entry_reference.py \
  <ORG_UUID> --actor-reference TASK16_CONTROLLED_LINE
```

不要把這個command的raw stdout貼入本文件。將raw reference只交給受控QR／URL流程，並記錄reference UUID的遮罩值。

在不呼叫LINE外部API的前提下驗證Rich Menu設定：

```bash
LIFF_BASE_URL="${LIFF_BASE_URL}" \
SHELTER_ENTRY_REFERENCE="<RAW_REFERENCE_ONLY_IN_CONTROLLED_SHELL>" \
API_BASE_URL="${PUBLIC_API_ORIGIN}" \
$HOME/.local/bin/uv run python scripts/sync_line_rich_menu.py \
  --config infra/gcp-demo/line-rich-menu.yaml
```

預期輸出：

```text
Rich Menu 設定有效：strayhub-gcp-demo-volunteer-care
```

Task 16只執行dry-run；不得使用`--apply`，除非另有明確的LINE外部副作用授權與獨立發布任務。

## 6. Case A–D手機驗收

每個Case都要在實際手機LINE內操作，並使用至少一台iOS與一台Android裝置（若本輪只具備一種裝置，必須在結果中標記缺口）。測試前先清除上一個Case的LIFF session，避免把stale context當成通過證據。

### Case A：首次identity → NEW → PENDING

1. 使用沒有既有ORG-A binding/application的受控LINE identity。
2. 從ORG-A Rich Menu／LIFF URL進入。
3. 確認不要求StrayHub帳密，exchange結果為NEW，畫面顯示ORG-A context。
4. 進入志工報名、勾選同意、送出。
5. 確認畫面進入PENDING；不建立internal Session／Refresh credential。

預期：HTTP exchange `200 NEW`，submit成功後為PENDING；不記錄raw token/reference。

### Case B：管理員核准 → exact membership/grant

1. 以受控管理員帳號在ORG-A管理介面找到Case A application。
2. 核准一次；確認只建立ORG-A的有限期VOLUNTEER Membership與Grant。
3. 重新整理管理清單，確認重複核准不產生第二組projection。
4. 記錄遮罩後的application／decision reference、HTTP status與時間。

預期：核准成功；cross-organization projection數量為0；不得把管理員帳號或LINE user ID寫入證據。

### Case C：同一identity第二次進入 → ACTIVE → animal confirmation

1. 用Case A同一受控LINE identity重新開啟ORG-A LIFF URL。
2. 確認exchange結果為ACTIVE，無StrayHub帳密頁。
3. 確認internal session建立後導向`/animal-confirmation`。
4. 確認server-confirmed shelter context為ORG-A，`GET /v1/animals`回200，畫面只顯示ORG-A資料。
5. 在約360px手機尺寸完成animal selection並進入report entry；不要保存protected data截圖。

預期：ACTIVE才建立Session／Refresh；原始entry不因client改寫而跨organization；受保護資料只在context通過後顯示。

### Case D：ORG-A／ORG-B隔離與stale資料

1. 以同一受控LINE identity依序開啟ORG-A與ORG-B entry（該identity必須有兩邊明確授權）。
2. 每次確認後端重新解析exact organization，且畫面只顯示當次organization的shelter label、animals與draft。
3. 另以ORG-B-only identity開啟ORG-A entry。
4. 清除session後重新載入、使用back與reload，確認不短暫顯示前一個organization protected data。

預期：ORG-A與ORG-B各自建立正確context；ORG-B-only→ORG-A安全拒絕；cross-tenant資料顯示率為0%。

## 7. Session失效附加檢查

在Case C或D中讓受控session失效，確認：

- 第一個protected `401`觸發最多一次LIFF exchange。
- 並行或late `401`不增加exchange count。
- recovery成功回到原volunteer flow；失敗進入terminal「重新進入／回到LINE」。
- save mutation不自動重播；表單輸入仍可由使用者明確重試。
- recovery期間先卸載舊protected view，不顯示前一organization資料。

## 8. 遮罩後證據表

每次實際驗收另存一份不含secret／PII的結果，格式如下：

| 欄位                     | 值                                               |
| ------------------------ | ------------------------------------------------ |
| Evidence ID              | `T16-<YYYYMMDD>-<case>-<sequence>`               |
| UTC time                 | `<ISO-8601 UTC>`                                 |
| Device／OS／LINE version | `<masked non-sensitive description>`             |
| Web tunnel host          | `<hostname only>`                                |
| API tunnel host          | `<hostname only>`                                |
| LIFF config version      | `<non-sensitive version/reference>`              |
| Entry reference          | `<reference UUID prefix/last4 only>`             |
| Case                     | `A`／`B`／`C`／`D`                               |
| HTTP status observed     | `<status only>`                                  |
| Visible result           | `<short Chinese result>`                         |
| Screenshot               | `<masked screenshot path; no protected content>` |
| Result                   | `PASS`／`FAIL`／`BLOCKED`                        |
| Blocker／next action     | `<if applicable>`                                |

目前本文件只代表驗收方法；在填入真實時間、裝置與結果前，Task 18不得引用它作為真機PASS證據。
