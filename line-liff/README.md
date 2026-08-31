# 浪浪森友會 · LINE / LIFF 介面

依角色切換的 LINE 選單框架，對應四種使用情境。純前端、無 build、預設 mock 模式，
不需真實 LINE 憑證或後端即可展示與試填。

## 目錄
| 資料夾 | 對應角色選單 | 功能 |
|---|---|---|
| `demo/` | — | **Demo Hub**：流程展示 + 對接說明（先看這個） |
| `staff-animal/` | 工作人員 | 新增動物、更新健康紀錄（由 paw-village 衍生） |
| `volunteer/` | 志工 | 散步回報、志工報到 |
| `adopter/` | 領養人 | 我想領養、領養回報 |

## 本機啟動
```bash
./serve-demo.sh          # 預設 port 8080，或 ./serve-demo.sh 9000
```
然後開 http://localhost:8080/demo/

## 對接（上線）
每個介面的 `js/config.js`（或 staff 以外的單檔內 CONFIG）需填：
- `LIFF_ID`：各自的 LINE Login channel LIFF ID
- `API_BASE_URL`：StrayHub 後端根路徑（含 `/v1`，https）
- `MOCK_MODE` / `USE_MOCK_API`：上線改 `false`

後端側對接與端點合約見 repo：
- `docs/line-role-menu-framework.md`（角色→選單、綁定接點、腳本）
- `docs/staff-animal-line-input.md`（工作人員動物輸入端點）
