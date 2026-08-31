# 串接 LINE 帳號 — 逐步設定

目標：從 mock 切到真實 LINE，能用真實帳號跑「綁定 → 依角色切選單 → 開 LIFF 操作」。
本文只需做一次；之後換人綁帳號只用最後的「綁定帳號」那步。

> 需要你手動去 LINE Developers Console 取得的憑證，本文標為 🔑。程式端該填哪、該跑什麼都寫在下面。

---

## 0. 你會需要兩個 LINE channel

在 [LINE Developers Console](https://developers.line.biz/) 的一個 Provider 底下建立：

1. **Messaging API channel**（給 Bot / Rich Menu / 推播用）
   - 🔑 `Channel ID` → `LINE_CHANNEL_ID`
   - 🔑 `Channel secret` → `LINE_CHANNEL_SECRET`
   - 🔑 `Channel access token`（長期）→ `LINE_CHANNEL_ACCESS_TOKEN`
2. **LINE Login channel**（給 LIFF 登入 / 身分驗證用）
   - 🔑 `Channel ID` → `LINE_LOGIN_CHANNEL_ID`
   - 🔑 `Channel secret` → `LINE_LOGIN_CHANNEL_SECRET`
   - 在此 channel 下建立 **LIFF app**：🔑 `LIFF ID` → `LIFF_ID`、`NEXT_PUBLIC_LIFF_ID`
   - LIFF 的 **Endpoint URL** 填你的 HTTPS 網址（見第 3 步 tunnel），scope 勾 `openid`、`profile`

> 工作人員動物輸入等 LIFF 若要各自獨立，可再建多個 LIFF app，把各自的 LIFF ID 填進
> `line-liff/*/config.js` 或單檔 CONFIG 的 `LIFF_ID`。最簡單是先共用一個 LIFF。

---

## 1. 填 `.env`

複製 `.env.example` 成 `.env`，把上面 🔑 的值填進去，並設定：

```dotenv
APP_ENV=local
LINE_CHANNEL_ID=<你的 Messaging channel id>
LINE_CHANNEL_SECRET=<...>
LINE_CHANNEL_ACCESS_TOKEN=<...>
LINE_LOGIN_CHANNEL_ID=<你的 Login channel id>
LINE_LOGIN_CHANNEL_SECRET=<...>
LIFF_ID=<你的 LIFF id>
NEXT_PUBLIC_LIFF_ID=<同上>
LIFF_BASE_URL=https://liff.line.me/<你的 LIFF id>
```

> ⚠️ 只要 `LINE_CHANNEL_ID` 不再是 `fake-` 開頭，後端就會改用**真實** LINE 身分驗證
> （`identity_verification_adapter.py` 的判斷），mock 驗證自動關閉。

JWT 金鑰若還沒設，依 README 產生並填 `AUTH_JWT_ACTIVE_PRIVATE_KEY` / `_PUBLIC_KEY`。

---

## 2. 起本機服務 + 資料

```bash
cp .env.example .env   # 然後照第 1 步填
docker compose -f infra/local/docker-compose.yml up -d postgres minio
uv run alembic upgrade head
uv run python -m scripts.seed_local        # 建立 local-staff-a 等測試帳號
```

三個終端機分別跑 FastAPI(8001) / Next.js(3001) / Worker（見 README）。

---

## 3. 對外 HTTPS（LINE 一定要 https）

LINE Webhook 與 LIFF Endpoint 都必須是公開 HTTPS。用兩條獨立 tunnel（Web 與 API 不可共用）：

```bash
cloudflared tunnel --url http://127.0.0.1:3001   # Web / LIFF
cloudflared tunnel --url http://127.0.0.1:8001   # API / webhook
```

- Messaging channel 的 **Webhook URL** 填：`https://<API tunnel>/v1/line/webhook`，並「Verify」。
- LIFF app 的 **Endpoint URL** 填：`https://<Web tunnel>/`（或各 LIFF 的路徑）。

---

## 4. 建立並綁定 Rich Menu（依角色）

準備四張 2500×1686 底圖，放 `infra/local/rich-menu-images/{default,volunteer,adopter,staff}.png`，然後：

```bash
# 先 dry-run 確認設定無誤（不需憑證）
uv run python -m scripts.sync_line_role_menus

# 實際建立（需 LINE_CHANNEL_ACCESS_TOKEN）
uv run python -m scripts.sync_line_role_menus --apply --image-dir infra/local/rich-menu-images
```

腳本會印出「角色 → richMenuId」。把四個 id 填回 `.env`：

```dotenv
LINE_RICH_MENU_DEFAULT_ID=richmenu-xxxx
LINE_RICH_MENU_VOLUNTEER_ID=richmenu-xxxx
LINE_RICH_MENU_ADOPTER_ID=richmenu-xxxx
LINE_RICH_MENU_STAFF_ID=richmenu-xxxx
```

> 填了之後，綁定成功時後端會自動依角色 link 對應選單（`session_service.bind_line_identity`）。
> 全空則此功能自動略過，不影響綁定本身。重啟 FastAPI 讓新 env 生效。

---

## 5. 綁定帳號（串帳號的核心）

要知道你自己的 **LINE userId**（U 開頭 33 字元）。取得方式擇一：
- 用 LIFF 登入後 `liff.getProfile()` 的 `userId`（可暫時 console.log 出來）；或
- 加官方帳號傳一則訊息，看 webhook 收到的 `source.userId`（server log）。

把它綁到既有 StrayHub 帳號（例如工作人員 `local-staff-a`）：

```bash
uv run python -m scripts.bind_line_account bind \
  --username local-staff-a --line-user-id U0123456789abcdef0123456789abcdef

# 查詢 / 解綁
uv run python -m scripts.bind_line_account status --username local-staff-a
uv run python -m scripts.bind_line_account unbind --line-user-id U0123...
```

> 一個帳號通常只綁一個 LINE UID；帳號需剛好 1 個 active membership，
> 否則 webhook 會要求「在 LIFF 明確選擇收容所」。

---

## 6. 驗收流程

1. 用綁定的 LINE 帳號打開官方帳號 → 底部選單應是該角色的選單
   （工作人員 = staff 選單）。
2. 點「新增動物 / 更新健康紀錄」→ 收到 LIFF 連結 → 開啟表單。
3. LIFF 表單 `config.js` 的 `MOCK_MODE=false`、`USE_MOCK_API=false`、
   `API_BASE_URL` 指向 API tunnel 的 `/v1`。
4. 送出 → 打到後端。

---

## 還沒完成、會擋住第 6 步「送出」的一件事

工作人員「新增動物 / 更新健康紀錄」送出的目標端點**後端尚未實作**：
- `POST /v1/management/animals`
- `POST /v1/management/animals/{id}/health-records`

合約見 [`staff-animal-line-input.md`](staff-animal-line-input.md)。在後端補上前，
staff 表單維持 `USE_MOCK_API=true` 可完整走完 UI（送出只在 Console 印 payload）。
其餘（綁定、依角色切選單、志工/領養人選單占位）都能用真實帳號跑通。

## 檔案速查
- 綁定工具：`scripts/bind_line_account.py`
- 選單發佈：`scripts/sync_line_role_menus.py`
- 角色→選單：`services/api/app/application/line_rich_menu_routing.py`
- 綁定切換選單接點：`services/api/app/application/authentication/session_service.py`
- LIFF 介面：`line-liff/`（demo / staff-animal / volunteer / adopter）
