# Timeline and Calendar Contract

## 收容所日期

API 回應同時提供 `organization_timezone`、UTC instant 與本地顯示日期時間。`today`、bucket、日期篩選及 Timeline day 由後端依 Organization IANA timezone 判定，前端不得用瀏覽器 timezone 重新分組。查詢使用 `[local midnight, next local midnight)` 轉成 UTC half-open range。

timezone 變更後，未結案 future occurrence 維持同一 local wall-clock 並重新投影 UTC；其 deterministic id 不變。已結案 action 保存當時 timezone／offset／UTC snapshot，不重算。Calendar cursor 綁定 `timezone_version`；版本不同回 409 並要求刷新。

## Occurrence Identity

- public id = UUIDv5(`lineage_id`, `occurrence_index`)。
- scheduled instant、短月份 clipping、單次改期與 timezone 變更都不構成 identity。
- monthly 31 日在 2 月為最後一日，3 月恢復 31 日。
- 「本次及未來」使用相同 lineage 與 ordinal 切分 segment，過去結案資料及 id 不變。
- virtual item `version=0`；第一次 action 會建立 persisted projection 並回 `version>=1`。

## Agenda Buckets

`GET /v1/management/care-agenda` 回傳四個互斥 bucket 與各自 `total_count`：

1. `today_pending`：今天預定且尚未結案。
2. `overdue`：今天之前預定且尚未結案。
3. `today_resolved`：今天由人工完成、略過或取消的事項；item status 保留實際 terminal 值，UI 標題為「今天已處理」。
4. `next_seven_days`：從明天起七個完整 local days 的未結案事項。

改期 action 本身依 `acted_at` 是 Timeline event；改後 occurrence 依新 scheduled time 進入唯一適用 bucket。到達預定時間不自動寫狀態；吃藥逾期不能呈現為已給藥或漏藥。第一階段沒有提前提醒或 upcoming eligibility。

每個 bucket 獨立 cursor 分頁，page size 預設 50、最大 100。逾期 `total_count` 必須精確，不得以最近 N 日截斷。filter 至少包含 animal、reminder type、assignee、status 與 local date。

## Calendar

`GET /v1/management/care-calendar` 接受 local `date_from`／`date_to`，最多 366 日。回應依 occurrence 的 effective scheduled local date 分組並含 page cursor；已結案 occurrence 仍顯示在該 effective scheduled date。改期 action 依 acted local date 只出現在 Timeline，原日期不再保留第二筆有效待辦；新日期顯示唯一 pending occurrence。recurrence 全部由後端計算。對無期限 long-running daily series，實作以 ordinal arithmetic 直接求 range，不從 anchor 逐日生成全部歷史。

## Timeline Additive Shape

既有 `GET /v1/animals/{animalId}/timeline` 保留 `reports`、`has_report`、`report_count`。每個 day additive 新增：

- `has_activity`、`event_count`；
- `events[]`：已發生事實，`occurrence=actual`；
- `scheduled[]`：該日 planned pending item，`occurrence=scheduled`。

top-level 新增 `organization_timezone` 與 `open_reminders[]`，集中今天待辦及較早逾期項目。`events.kind` 為 `care_report | medical_record | reminder_completed | reminder_skipped | reminder_rescheduled | reminder_cancelled`。`scheduled.kind=care_reminder`。UI 必須用文字／圖示標示「已發生」與「預定／待處理」，不能只靠顏色。

## 空值與錯誤狀態

後端／前端需區分：成功但無事件、今天有事件但無待辦、仍有待辦、有逾期待辦、載入失敗、權限不足及 stale conflict。API error 使用既有 `code`、正體中文 `message`、`request_id`；409 可帶最新安全狀態與 `timezone_version`，但不得洩漏其他 tenant 資料。
