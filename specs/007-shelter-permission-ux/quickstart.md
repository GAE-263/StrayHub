# Quickstart: 收容所權限管理介面改善

## 前置條件

- PostgreSQL、FastAPI 與 Next.js 本機服務已依專案 README 啟動。
- 已完成 local seed，並可使用：
  - 帳號：`local-shelter-admin-a`
  - 密碼：`local-only-password`
- 服務網址：`http://127.0.0.1:3001`

## 自動化驗證

在 repository root 執行：

```bash
./apps/web/node_modules/.bin/vitest run 'apps/web/app/(management)/shelters/page.test.tsx'
./apps/web/node_modules/.bin/tsc --noEmit --project apps/web/tsconfig.json
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/contract/test_organization_management_contract.py
git diff --check
```

預期結果：前端 page tests、TypeScript typecheck、organization management contract tests 全數通過，且沒有 whitespace error。

## 本機真人驗證

1. 開啟 `http://127.0.0.1:3001/login`，使用上述管理員帳號登入。
2. 開啟 `http://127.0.0.1:3001/shelters`。
3. 確認頁面主標題是「權限管理」，Membership 清單以姓名與帳號辨識，不以 UUID 作主要名稱。
4. 確認 STAFF 顯示醫療資料權限狀態；VOLUNTEER 與 SHELTER_ADMIN 不顯示不適用的醫療權限 checkbox。
5. 確認 active、expired、revoked 等狀態仍能辨識，角色選擇與停用帳號操作仍存在。
6. 確認頁面顯示「台灣各地收容所統一使用 Asia/Taipei（台灣時間）」且不存在時區選單或「儲存時區」按鈕。
7. 使用瀏覽器 1440px、768px、360px 寬度重新載入，確認 Membership 卡片沒有重疊、文字截斷或需要水平捲動才能操作的控制項。

## 跨租戶安全檢查

- 以 A 收容所管理員開啟清單時，只能看到 A 的 Membership 與 A 使用者姓名／帳號。
- 不得透過修改網址中的 organization id 取得另一收容所的 Membership identity。
- 既有未授權角色仍收到原有拒絕結果，且不因新增顯示欄位而洩漏其他收容所資料。
