# Phase 0 Research：毛孩日記管理頁

## 1. Management shell 與 tenant context

**Decision**：新增 `/growth-diary` management route，沿用 `ManagementLayout`、shared navigation 與 `authFetch`；前端不讀取或傳送 `organization_id` 作授權依據。

**Rationale**：現有 shell 已驗證登入、role、active shelter context，切換收容所時會 unmount tenant subtree；`authFetch` 會中止舊 organization scope 的 request。這可防止 A 收容所的延遲回應在切到 B 後重新顯示。

**Alternatives considered**：獨立 layout 會複製 auth/context；使用 sessionStorage organization id 會把 UI hint 誤當 authority，均拒絕。

## 2. 資訊架構與視覺方向

**Decision**：採「返家後生活札記」時間軸，以提交時間節點串接響應式日記卡；卡片依序呈現動物識別、領養人提交照片的安全正規化版本／原始文字、AI 工作人員摘要與給領養人的回覆。桌面照片與內容雙欄，手機上下堆疊，不使用 table。

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

**Decision**：list 回 `photo_endpoint`；前端以 `authFetch` 取得 Blob、建立 object URL，unmount／tenant switch 時 revoke。新增 `GET /v1/management/growth-diary-entries/{entry_id}/photo`，先驗證 role、active organization、entry id + organization，再從 private storage 以既有 `ObjectStoragePort.get()` buffered read 取得最多 2 MB 的 final WebP；runtime 回覆固定 `Content-Type: image/webp`、`Cache-Control: private, no-store`、`X-Content-Type-Options: nosniff`，OpenAPI MIME 只由 `content.image/webp` 表達，不把 `Content-Type` 重複列為 response header。不存在、跨 tenant、無可信 `photo_content_type`、無照片與 storage failure 統一 404。

**Rationale**：production MinIO 使用容器內 hostname，瀏覽器無法解析；`<img>` 又不能附帶 sessionStorage Bearer token。authenticated Blob 能沿用 request-scope cancellation，也不把 credential 放 URL。

**Alternatives considered**：繼續回 internal presigned URL、公開 MinIO、把 token 放 query string都違反 production reachability 或 private-media 安全；新增 streaming port 在 2 MB final ceiling 下沒有必要，會擴大 architecture scope。

## 6. AI status、標示與 provenance

**Decision**：AI 區塊固定標示「AI 產生、未經人工確認、非醫療診斷」。新增 `pending/succeeded/failed/unconfigured/not_applicable` status，以及 provider、model name/version、prompt version、output schema version、raw output、analyzed time。舊資料缺少來源時顯示 `legacy_missing`，不得用目前設定值假造歷史。

**Rationale**：現有三個 nullable AI 欄位無法區分等待、失敗、無憑證或 photo-only，也不符合 Constitution 的模型／prompt／raw output 追溯要求。`concern` 只能是描述性建議，由人員主動篩選，不得成為診斷或自動排序。

**Alternatives considered**：前端以 null 推測「等待分析」不可靠；把 concern 當正式健康等級違反 AI 邊界；完整人工覆核 mutation 留待獨立 feature，第一版保持唯讀。

## 7. UI states 與測試層次

**Decision**：重用 `LoadingState`、`PermissionDeniedState`、`ErrorState`、`EmptyState`、Field/Input/Select/Badge/Button；真正 empty、filtered empty、403、network error、image error 各自提供可行下一步。測試分 contract、API/RLS、Vitest 與 Playwright tenant switch/responsive/keyboard/axe 四層。

**Rationale**：前端導覽不是安全邊界；真實 PostgreSQL isolation 才能證明 A/B 隔離，瀏覽器測試才能證明舊 response 與 Blob 不殘留。page-scoped CSS 可避免繼續膨脹 globals。

**Alternatives considered**：只測 pure filter 或只測 E2E 都無法完整覆蓋契約、安全與錯誤定位。

## 8. 既有圖片處理與 WebP normalization

**Decision**：直接擴充 `services/api/app/application/media_sanitization.py` 與既有 `MediaProcessingService`，不建立 Growth Diary 專用 image service。Growth Diary 呼叫明確選用 WebP normalization policy；既有其他 media caller 的輸出契約不在本 feature 內變更。接受 MIME 與實際格式一致的 JPEG、PNG、WebP，原始 compressed input 最大 10 MB；只把 final sanitized WebP 傳給 storage。

**Rationale**：現有流程已集中處理格式白名單、重新編碼、EXIF 移除、checksum 與 `ObjectMetadata`，且 Pillow 已是 runtime dependency。沿用同一 boundary 可避免安全政策分叉。現況會 `source.load()` 後才處理內容並保持原輸出格式；planned behavior 將加入 pre-decode pixel gate、orientation、第一幀、alpha、resize 與 WebP fallback。

**Alternatives considered**：平行 image processor 會產生兩套媒體安全規則；保存 original 再離線壓縮會留下過大及含 metadata 的物件；兩者均拒絕。

## 9. Pixel gate 與 Pillow decompression-bomb 配合

**Decision**：`Image.open()` 只讀 header 後，立即取得 width/height 並在任何 `source.load()`、`ImageOps.exif_transpose()` 或 frame copy 前檢查 `width * height <= 25_000_000`。同時將 Pillow `DecompressionBombWarning` 在此流程中提升為可捕捉的拒絕錯誤，並捕捉 `DecompressionBombError`；application-level 25M limit 是正式產品邊界，Pillow threshold 是額外 defense-in-depth。

**Rationale**：目前環境的 `Image.MAX_IMAGE_PIXELS` 是 89,478,485；Pillow 在超過該值時發出 warning，超過約兩倍時拋出 error，均高於本 feature 的 25M 限制。只依賴 Pillow 預設值或 10 MB compressed byte limit，不能阻止小型壓縮檔造成過高 decode memory。header 解析本身仍可能遭遇 Pillow warning/error，因此必須在 open 周圍配置 warning handling，再執行更低的 application gate。

**Alternatives considered**：在 `source.load()` 後才檢查已經失去記憶體保護效果；全域修改 `Image.MAX_IMAGE_PIXELS` 會影響其他 Pillow consumer；只忽略 warning 則降低 defense-in-depth。三者均拒絕。

## 10. Orientation、animation、alpha 與固定 fallback

**Decision**：通過格式與 pixel gate 後，選取 animated input 的第一 frame，套用 EXIF orientation，再移除 EXIF/metadata；保留 alpha channel，不放大小圖片。輸出依序嘗試：長邊最多 1600 px、WebP quality 82；若大於 2 MB，以相同尺寸 quality 72；仍過大時長邊最多 1280 px、quality 68；最終仍大於 2 MB 則拒絕。每次嘗試都只存在記憶體，storage 只收到最後成功 bytes。

**Rationale**：固定且可測試的 fallback 可限制 storage 與 photo response 上限，又不需背景壓縮任務。WebP 支援 alpha，能統一 JPEG/PNG/WebP 的新資料 MIME。orientation 必須在 resize 前套用，否則長邊判斷可能錯置；不 upscale 可避免小圖無益放大。

**Alternatives considered**：無限品質迴圈難以預測；保存多尺寸或原檔增加 storage ownership；移除 alpha 或一律轉 RGB 會破壞透明圖片。均不採用。

## 11. DB transaction 與 orphan compensation

**Decision**：per-event webhook orchestration 擁有新 Growth Diary object 的 compensation token。`MediaProcessingService.store_cleaned()` 成功後登記 `organization_id + object_key`；只有外層 `async with session.begin()` 成功完成 commit 後才清除。insert、flush、handler 或 commit 任一失敗時，rollback 後以現有 `ObjectStoragePort.delete()` 補償刪除。Growth Diary handler 只準備成功 reply 與 AI task 參數，transaction commit 後才由 webhook orchestration 送出／註冊。cleanup failure 使用 `logger.exception` 記錄固定事件名 `growth_diary_orphan_cleanup_failed` 與 correlation 欄位，不覆蓋 root cause、不向使用者暴露 key。

**Rationale**：目前 `_handle_growth_diary_message()` 在外層 webhook transaction 內先 put object 再 `add_entry()`，並在 commit 前送出成功 reply；真正 commit 發生在 handler 返回後，所以單純在 handler 內 try/except 無法捕捉 commit failure，也可能在 commit failure 後已告知使用者成功。將 compensation ownership與 Growth Diary post-commit side effect 放在既有 per-event transaction boundary，是涵蓋完整失敗面的最小修改，也不需要 distributed transaction。既有 event-based deterministic object key 讓相同 webhook retry 覆寫同一 scope/key，不會擴散成多個 orphan。

**Alternatives considered**：只捕捉 DB insert failure 漏掉 commit failure；兩階段 commit、saga framework或新 background cleanup service超出範圍；忽略 delete failure無法觀測。均拒絕。

## 12. Roles、raw output 與 audit policy

**Decision**：STAFF、SHELTER_ADMIN、具有 active shelter context 的 PLATFORM_ADMIN 均可讀 list/detail/raw output/photo；VOLUNTEER、無 active shelter context 與其他 organization 均拒絕。list 只含 analysis/provenance summary，完整 provenance 與 raw output 只在 detail。第一版不為 list/detail/photo/raw-output read 新增 audit event。

**Rationale**：現有 `require_staff_or_admin()` 已涵蓋三個 management role 且要求 active organization；後端與 RLS 仍是授權邊界。Constitution VIII 要求重要資料異動保留 audit，本 feature 是高頻 read-only flow，未新增 read audit 不構成 mutation audit 缺口；錯誤 logging、authentication、authorization 與既有 audit 行為不變。

**Alternatives considered**：另建 permission abstraction 重複既有 role gate；把 raw output 放 list 增加不必要曝光與 payload；把每次照片請求寫入 mutation audit log 會造成高頻噪音。均不採用。

## 13. Canonical OpenAPI ownership

**Decision**：`specs/011-growth-diary-management/contracts/growth-diary-management.openapi.yaml` 作為 feature design contract；實作階段必須將 paths/schemas 合併到既有唯一 canonical `specs/001-volunteer-care-report/contracts/openapi.yaml`，再由現有 `packages/contracts` script 生成 TypeScript。

**Rationale**：目前 `packages/contracts/package.json` 與 `check-generated.mjs` 都固定讀取 001 canonical。只更新 011 contract 不會改變 generated types，因此 plan 必須明確包含 canonical merge。

**Alternatives considered**：為單一 feature 改成多契約生成或新增 bundler 會擴大 tooling scope；讓前端手寫型別會產生第二份不可驗證契約。均不採用。
