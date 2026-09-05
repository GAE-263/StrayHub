# Remote Management Demo 操作手冊

Shared management profile 是本機展示能力。Phase D 只加入 rollback 基礎，不代表已授權公開啟用。
啟動真實 public tunnel 前，仍必須完成 012 T008 事件處置與 Phase E activation gate。

## 一鍵啟動本機 demo 與 ngrok

先在 `.env` 設定 `NGROK_URL`、`LIFF_ID` 與 `SHELTER_ENTRY_REFERENCE`，再執行：

```bash
./scripts/demo-shared-management.sh
```

腳本會互動式讀取新的 demo 密碼、執行 `./scripts/demo.sh check` 建立／驗證 synthetic demo
資料，要求授權操作者輸入代號與 `ACTIVATE`，再從已提交的 T055～T057 去敏驗收紀錄建立當次
暫存 activation evidence 並啟動 `shared-demo-production`。暫存 evidence 會在結束時刪除；密碼只
存在當次 process environment，不會寫入 URL、檔案或輸出。外部測試者應使用
`demo-furkids-admin`，並透過安全管道另外取得密碼。

若環境 owner 已另外提供有效 evidence，仍可明確指定：

```bash
./scripts/demo-shared-management.sh --activation-evidence /secure/path/activation-evidence.json
```

測試完成後按 `Ctrl-C`，helper 會停止 FastAPI、Next.js、nginx、worker 與 ngrok。不要同時先執行
`./scripts/demo.sh serve`，否則會佔用相同的 API/Web ports。

## 依序 rollback

在 repository root 對 helper 擁有的 runtime directory 執行：

```bash
uv run python scripts/rollback_remote_management.py \
  --runtime-dir /absolute/path/to/current/public-tunnel-runtime
```

Session revocation 永遠使用 application runtime 的 `DATABASE_URL`。即使環境另有供 migration
使用的 `DATABASE_MIGRATION_URL`，rollback 也不會改用該連線，以免 gateway 與 session revoke
指向不同資料庫。

指令固定依照下列 fail-closed 順序執行：

1. 產生並語法檢查 `line-only` gateway config。
2. 原子替換並 reload 本機 nginx gateway config。
3. 確認 `/login` 與 `/v1/auth/login` 都回傳 404。
4. 確認 LINE webhook route 仍可抵達 API。
5. 在單一 database transaction 中，只撤銷 `remote_management_demo` sessions 與其 active refresh
   records。

若 gateway 切換或任一 probe 失敗，指令不會執行 session revocation，並以 non-zero 結束。成功後
重複執行是安全的，新增撤銷數會是零。

## Evidence 與安全邊界

成功輸出是一個 JSON object，內容只有 UTC 起訖時間、耗時秒數、固定 rollback reason、route probe
結果與 aggregate revoke counts；不包含 user ID、session ID、refresh value、Authorization header、
password、query string 或 request body。請連同 operator identity 與 nginx validation output 保存。

復原目標為五分鐘，超時會使指令失敗。Local 與 LIFF sessions 會刻意保留；migration 前的既有
sessions 會分類為 `legacy` 並保留。Rollback 不會依 role、tenant、timestamp 或 IP 猜測 origin。

此指令不會 rotate 先前曝光的 demo credential、不會清除 browser/ngrok history、不會檢查 remote
logs、不會啟動 ngrok，也不會完成 Phase E activation gate。Feature 012 中列出的這些項目仍為
`MANUAL ACTION REQUIRED`。
