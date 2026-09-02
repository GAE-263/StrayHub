# Phase 0 Research：毛孩日記管理頁

## 1. Management shell 與 tenant context

**Decision**：新增 `/growth-diary` management route，沿用 `ManagementLayout`、shared navigation 與 `authFetch`；前端不讀取或傳送 `organization_id` 作授權依據。

**Rationale**：現有 shell 已驗證登入、role、active shelter context，切換收容所時會 unmount tenant subtree；`authFetch` 會中止舊 organization scope 的 request。這可防止 A 收容所的延遲回應在切到 B 後重新顯示。

**Alternatives considered**：獨立 layout 會複製 auth/context；使用 sessionStorage organization id 會把 UI hint 誤當 authority，均拒絕。

## 2. 資訊架構與視覺方向

**Decision**：採「返家後生活札記」時間軸，以提交時間節點串接響應式日記卡；卡片依序呈現動物識別、原始照片／文字、AI 工作人員摘要與給領養人的回覆。桌面照片與內容雙欄，手機上下堆疊，不使用 table。

**Rationale**：時間是日記真正的結構；照片、長文字與 AI 分區放入 table 會在手機產生橫向捲動，也弱化原始資料與衍生資料的界線。

**Design tokens**：沿用既有管理後台的墨綠 `#19332f`、松綠 `#16745c`、霧綠 `#e2f1e9`、琥珀 `#a86d24`、淡灰綠 `#f4f8f5` 與危險紅 `#a34040`。標題使用現有 `Noto Sans TC`／system stack 700–800 weight，正文沿用 Inter／`Noto Sans TC`；不新增字型或全域品牌系統。

**Signature**：返家後時間軸是唯一視覺特色；concern 只在 AI 區塊顯示「建議人工查看」，不覆蓋原始日記。

**Alternatives considered**：table 不適合窄螢幕；masonry 破壞時間順序；每筆另開 detail route 增加不必要導航。只對 AI raw output 使用 lazy detail contract。

## 3. List query、filter 與 pagination

**Decision**：GET list 支援 `query`、`mood`、`page`、`page_size`；預設 50、上限 100，排序固定 `created_at DESC, id DESC`，回應包含 `items/page/page_size/total`。query 搜尋同 organization 的 Animal.name／shelter_number，mood 支援 `all/concern/positive/neutral/unanalyzed`。

**Rationale**：日記會持續累積，現有無界限查詢且逐筆產生照片 URL，長期無法維持首屏目標。server filter 必須在 count、order 與 offset 前套用，才能搜尋完整收容所歷史。

**Alternatives considered**：無分頁與 client-only filter 無法保證完整結果；第一版全文索引與搜尋領養人個資超出範圍。

## 4. API 與 TypeScript 契約

**Decision**：新增 Pydantic list/detail models 與 `response_model`，同步 canonical OpenAPI 和 generated `packages/contracts/src/openapi.ts`；前端型別引用 generated contract。

**Rationale**：目前 endpoint 只宣告 generic `dict`，nullable、datetime、AI status 與 pagination 沒有 runtime 驗證。

**Alternatives considered**：page 內手寫 TypeScript type 或只寫文件都會形成不可驗證的第二份契約。

## 5. Private photo delivery

**Decision**：list 回 `photo_endpoint`；前端以 `authFetch` 取得 Blob、建立 object URL，unmount／tenant switch 時 revoke。新增 `GET /v1/management/growth-diary-entries/{entry_id}/photo`，先驗證 role、active organization、entry id + organization，再從 private storage 讀取；回覆使用已保存的 sanitized content type、`Cache-Control: private`、`nosniff`。不存在、跨 tenant、無照片與 storage failure 統一 404。

**Rationale**：production MinIO 使用容器內 hostname，瀏覽器無法解析；`<img>` 又不能附帶 sessionStorage Bearer token。authenticated Blob 能沿用 request-scope cancellation，也不把 credential 放 URL。

**Alternatives considered**：繼續回 internal presigned URL、公開 MinIO、把 token 放 query string都違反 production reachability 或 private-media 安全。

## 6. AI status、標示與 provenance

**Decision**：AI 區塊固定標示「AI 產生、未經人工確認、非醫療診斷」。新增 `pending/succeeded/failed/unconfigured/not_applicable` status，以及 provider、model name/version、prompt version、output schema version、raw output、analyzed time。舊資料缺少來源時顯示 `legacy_missing`，不得用目前設定值假造歷史。

**Rationale**：現有三個 nullable AI 欄位無法區分等待、失敗、無憑證或 photo-only，也不符合 Constitution 的模型／prompt／raw output 追溯要求。`concern` 只能是描述性建議，由人員主動篩選，不得成為診斷或自動排序。

**Alternatives considered**：前端以 null 推測「等待分析」不可靠；把 concern 當正式健康等級違反 AI 邊界；完整人工覆核 mutation 留待獨立 feature，第一版保持唯讀。

## 7. UI states 與測試層次

**Decision**：重用 `LoadingState`、`PermissionDeniedState`、`ErrorState`、`EmptyState`、Field/Input/Select/Badge/Button；真正 empty、filtered empty、403、network error、image error 各自提供可行下一步。測試分 contract、API/RLS、Vitest 與 Playwright tenant switch/responsive/keyboard/axe 四層。

**Rationale**：前端導覽不是安全邊界；真實 PostgreSQL isolation 才能證明 A/B 隔離，瀏覽器測試才能證明舊 response 與 Blob 不殘留。page-scoped CSS 可避免繼續膨脹 globals。

**Alternatives considered**：只測 pure filter 或只測 E2E 都無法完整覆蓋契約、安全與錯誤定位。
