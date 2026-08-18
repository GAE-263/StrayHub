# Research: 收容所管理員人數與權限調整確認

## Decision 1：沿用既有 Membership 欄位，不新增政策資料表

- **Decision**：以既有 `OrganizationMembership.role = SHELTER_ADMIN` 與 `status = active` 計算每個收容所的啟用中管理員；不新增 `ShelterAdminPolicy`、管理員快照或其他第二套角色來源。停用、過期、封存的 Membership 不計入啟用中數量，但其歷史資料保留。
- **Rationale**：目前資料模型已能表達角色、狀態、封存與志工授權，需求是對既有狀態加上跨列 invariant。新增政策資料表會增加 migration、同步與資料對帳負擔；本 feature 的上下限固定為 1 與 2，不需要可配置政策。
- **Alternatives considered**：新增每個收容所政策資料列可集中保存上下限，但會使固定規則多一個可被錯誤修改的來源；只在前端計算則無法防止直接 API 呼叫或並發操作。

## Decision 2：以 Organization row lock 序列化同一收容所的權限異動

- **Decision**：所有會建立、提升、重新啟用、停用、降權或封存／恢復 `SHELTER_ADMIN` 的 mutation，在同一資料庫交易中先鎖定目標 `Organization`，再讀取最新 Membership、計算 before／after 管理員數量，驗證通過後才寫入。只改醫療資料權限或志工授權時也沿用同一個 mutation boundary，但不改變管理員數量。
- **Rationale**：`Organization` 是所有 Membership 共用且必然存在的租戶鎖定點，不需要新增 schema；同一收容所的請求依序檢查，可防止兩個「目前都是一位」的提升同時成功而形成三位，也防止兩個停用同時把最後管理員移除。
- **Alternatives considered**：只使用 `count()` 再寫入會有 check-then-act race；新增單一政策列雖可鎖定，但對固定收容所規則而言是額外資料來源；依賴前端 disabled 狀態不能保護 API。

## Decision 3：先建立完整 before／after projection，再套用變更

- **Decision**：Service 將角色、Membership 狀態、醫療資料權限與志工授權狀態視為一次變更的候選結果；更新、封存與恢復請求必須帶入 Modal 開啟時讀到的 `access_version`，鎖定後若版本不符即拒絕且要求重新載入。先驗證角色白名單、志工狀態、管理員上下限、操作者 scope 與目標最新狀態，全部通過後才一次套用欄位並遞增版本。建立帳號時先檢查管理員名額，再建立 User 與 Membership。
- **Rationale**：目前 `update_membership` 會依輸入順序直接修改物件；若同一請求包含多個欄位，任何後續檢查失敗都可能留下記憶體中已改欄位。完整 projection 可確保錯誤時沒有部分結果，也能正確判斷「角色從 STAFF 變 SHELTER_ADMIN 且狀態同時變 disabled」這類最終狀態。
- **Alternatives considered**：逐欄位驗證與 rollback 需要記錄所有原值，容易漏欄位；只在 API 層分拆成多個請求會增加部分成功與稽核不一致風險。

## Decision 4：成功與拒絕都沿用 AuditService

- **Decision**：成功的 Membership mutation 繼續使用既有 action（例如 `membership.updated`、`membership.archived`、`membership.restored`）；人數下限／上限、目標狀態衝突與權限拒絕以相同 organization scope 寫入 `AuditRecord`，`result = denied`、`reason` 使用 domain code，並在錯誤回應前完成 rollback／commit 邊界處理。不得把拒絕細節放入 Toast。
- **Rationale**：既有 `AuditRecord` 已支援 before／after／reason／result 與 organization scope，沿用可讓管理頁和稽核查詢追溯成功及失敗嘗試。重要權限操作只記成功會遺漏防護是否實際生效的證據。
- **Alternatives considered**：另建 permission audit 表會產生第二套稽核來源；只記 log 無法由現有管理稽核入口查詢；前端自己記錄無法防止 API 呼叫繞過。

## Decision 5：共用確認 Modal 與 Toast，不引入新 UI 套件

- **Decision**：新增可重用的 Membership 權限確認元件，使用既有 `AlertDialog` 語意，接收目標身份、動作、前後權限與管理員數量影響；`/shelters` 與 `/shelters/archived` 共用。成功回應後使用既有 `Toast`，由頁面提供左下角固定位置與可及性；取消、錯誤與結果不明不顯示成功 Toast。
- **Rationale**：專案已有原生 dialog 的 Escape、focus return、alertdialog 測試與 Toast 的 `role=status`／`aria-live`；重用能保持視覺與鍵盤行為一致，也避免導入外部套件。
- **Alternatives considered**：繼續使用 `window.confirm` 無法呈現前後差異且不易測試；只在頁首 Alert 顯示成功結果不符合左下角需求；導入新通知套件會擴大依賴與樣式範圍。

## Decision 6：所有有效權限 mutation 都必須先確認

- **Decision**：角色切換、啟用／停用、醫療資料權限切換、封存／恢復與任何會改變有效 Membership 權限的操作，統一先進入待確認狀態；建立帳號的流程維持既有建立 Modal，但若建立結果是啟用中的 `SHELTER_ADMIN`，仍由後端套用同一名額檢查。Modal 關閉後不保留前一次敏感或待提交狀態。
- **Rationale**：使用者要防止誤按，且不同按鈕不能各自維持不同確認語意；後端人數檢查與前端預覽分工，前端只提供可理解的預覽，不能取代安全驗證。
- **Alternatives considered**：只確認停用會漏掉角色提升與醫療資料授權；只確認危險動作會讓「授權」仍可被誤按；用瀏覽器原生 confirm 無法清楚呈現結果人數與鍵盤可及性。
