# Research: 收容所成員封存與權限管理版型改善

## Decision 1: 封存 Membership，不永久刪除 User

- **Decision**: 將封存視為目前收容所 Membership 的生命週期狀態；User、照護回報、醫療資料與 Audit 保留。封存狀態從一般頁面隱藏，透過獨立查詢頁面恢復。
- **Rationale**: 使用者與 Membership 被多種歷史資料引用，且同一 User 可能在不同收容所擁有不同權限。只封存當前 organization 的 Membership 可維持資料追溯與租戶隔離。
- **Alternatives considered**: 直接刪除 User／Membership 會破壞歷史關聯；只把 User 設為停用則無法區分某一收容所的權限撤銷，也無法支援其他收容所繼續使用。

## Decision 2: 保存封存前狀態，恢復時避免誤轉為啟用

- **Decision**: Membership 增加封存前狀態與封存時間／操作者資料；恢復時回到封存前狀態。若志工有效期間已過，恢復後仍維持已過期，不直接變成啟用中。
- **Rationale**: 管理員或工作人員可能在封存前已停用，志工可能已過期；單純把所有恢復結果設為 active 會擴大權限。
- **Alternatives considered**: 一律恢復為 active 較簡單，但會違反最小權限並改變原有狀態語意。

## Decision 3: 正常頁與封存頁採兩個使用者入口

- **Decision**: 正常管理頁維持 `/shelters`，新增 `/shelters/archived` 顯示目前收容所的封存成員，兩者共用相同的角色分區與身份呈現規則。
- **Rationale**: 封存資料不應干擾日常作業，但管理員仍需可搜尋、核對與恢復；獨立 route 也讓權限與測試邊界明確。
- **Alternatives considered**: 在同一頁加入展開／收合的封存清單會讓頁面狀態與資料量持續增加，且不符合「預設收起來」的需求。

## Decision 4: 版型借鑑管理後台模式，不直接引入外部模板

- **Decision**: 參考 shadcn/ui dashboard blocks 的頁面層級與資料表模式，以及 Flowbite user list 的成員身份／狀態／操作排列；使用專案既有 React UI 元件與 CSS 實作。
- **Rationale**: 專案已有 Card、Badge、Dialog、響應式 CSS 與測試基礎，直接引入模板會增加樣式衝突與依賴維護成本。參考成熟模式仍可改善資訊層級。
- **Alternatives considered**: 引入整套 Tabler、Flowbite 或 shadcn 元件庫會擴大本次變更範圍，且可能與現有 tokens、無障礙行為與元件 API 不一致。
- **Sources**: [shadcn/ui dashboard blocks](https://ui.shadcn.com/blocks?category=dashboard)、[Flowbite users list](https://flowbite.com/application-ui/demo/users/list/)、[Flowbite tables](https://flowbite.com/docs/components/tables/)

## Decision 5: 建立帳號沿用既有 Dialog

- **Decision**: 將建立帳號表單移入既有 `Dialog`，在權限管理頁首提供主要操作按鈕；Modal 需支援取消、Escape、返回焦點、錯誤保留非敏感欄位與成功後清除密碼。
- **Rationale**: 專案已具備原生 dialog 的焦點與 modal 行為，重用可降低依賴與維護成本，並符合管理員不需滾動到頁尾的需求。
- **Alternatives considered**: 新增外部 modal 套件沒有必要；保留頁尾表單則無法解決主要操作的可見性問題。
