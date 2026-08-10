# Management Workbench Gate Evidence

狀態：待完成 T272、T281、T289、T298、T305、T307 與 T308。此文件只提供去識別化驗收欄位，未填資料不得視為 Feature Completion。

## 自動化 Gate

| Gate | 結果 | 證據／命令 | 版本／批次 |
|---|---|---|---|
| `uv run ruff check .` | 待填 | 待填 | 待填 |
| `uv run ruff format --check .` | 待填 | 待填 | 待填 |
| `uv run pytest` | 待填 | 待填 | 待填 |
| `npm --prefix apps/web run quality` | 待填 | 待填 | 待填 |
| `npm --prefix apps/web run build` | 待填 | 待填 | 待填 |
| `npm --prefix packages/contracts run check` | 待填 | 待填 | 待填 |
| T307 A／B Context Matrix | 待填 | 待填 | 待填 |

## 角色／Context／可發現性驗收

| 角色代碼 | Context 代碼 | 首頁 → Animals → Profile → Timeline | Reports／Settings／AI／Audit 可見性 | 401／409／403 | 失敗與協助 |
|---|---|---|---|---|---|
| 待填 | A | 待填 | 待填 | 待填 | 待填 |
| 待填 | B | 待填 | 待填 | 待填 | 待填 |

## 未完成與阻擋

- 不填入姓名、帳號、電話、照片、正式收容所識別或其他可直接識別資料。
- 真人受測者資料分別記錄於 volunteer／staff evidence；本文件只整合結果與阻擋原因。
- 在 T254、T255、T256、T272、T281、T289、T298、T305、T307 及本文件全部通過前，Feature Completion 維持未完成。
