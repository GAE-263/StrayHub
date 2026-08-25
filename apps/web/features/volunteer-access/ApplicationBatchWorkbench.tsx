"use client";

import React, { useMemo, useRef, useState } from "react";

import { MembershipPermissionDialog } from "../../components/management/MembershipPermissionDialog";
import { Alert } from "../../components/ui/alert";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Checkbox } from "../../components/ui/checkbox";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Table } from "../../components/ui/table";
import { Toast } from "../../components/ui/toast";
import { EmptyState } from "../../components/management/StateViews";

type Application = {
  id: string;
  display_name: string;
  status: string;
  version: number;
};

type Batch = {
  id: string;
  status: string;
  requested_count: number;
  processed_count: number;
  succeeded_count: number;
  conflict_count: number;
  failed_count: number;
};

type BatchItem = {
  application_id: string;
  expected_version: number;
  result: string;
  error_code?: string | null;
};

function isTerminalBatch(batch: Batch): boolean {
  return (
    batch.status === "completed" || batch.status === "completed_with_errors"
  );
}

function shouldReloadAfterTerminalBatch(batch: Batch): boolean {
  return batch.status === "completed" || batch.succeeded_count > 0;
}

function utcValue(localValue: string): string | null {
  if (!localValue) return null;
  const parsed = new Date(localValue);
  return Number.isNaN(parsed.valueOf()) ? null : parsed.toISOString();
}

export function ApplicationBatchWorkbench({
  applications,
  matchingCount,
  loading = false,
  filter,
  onSubmit,
  onLoadItems,
  onLoadBatch,
  onBatchTerminalSuccess,
  onViewApplicant,
}: {
  applications: Application[];
  matchingCount: number;
  loading?: boolean;
  filter:
    | {
        status: "pending";
        service_date: string;
        unassigned?: false;
        submitted_from?: string;
        submitted_to?: string;
      }
    | {
        status: "pending";
        service_date?: never;
        unassigned: true;
        submitted_from?: string;
        submitted_to?: string;
      };
  onSubmit?: (payload: object) => Promise<Batch | void> | Batch | void;
  onLoadItems?: (batchId: string) => Promise<BatchItem[]>;
  onLoadBatch?: (batchId: string) => Promise<Batch>;
  onBatchTerminalSuccess?: (batch: Batch) => void | Promise<void>;
  onViewApplicant?: (applicationId: string) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [allFiltered, setAllFiltered] = useState(false);
  const [decision, setDecision] = useState<"approve" | "reject">("approve");
  const [reason, setReason] = useState("");
  const [defaultValidFrom, setDefaultValidFrom] = useState("");
  const [defaultExpiresAt, setDefaultExpiresAt] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [results, setResults] = useState<BatchItem[]>([]);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const operationId = useRef<string | null>(null);
  const terminalNotifiedBatch = useRef<string | null>(null);
  const selectedSet = useMemo(() => new Set(selected), [selected]);

  function decisionItems(ids: Set<string>) {
    return applications
      .filter((item) => ids.has(item.id))
      .map((item) => ({
        application_id: item.id,
        expected_version: item.version,
        expires_at: utcValue(overrides[item.id]),
      }));
  }

  function buildPayload(retryItems?: BatchItem[]) {
    operationId.current ??= crypto.randomUUID();
    const defaultPeriod = {
      default_valid_from: utcValue(defaultValidFrom),
      default_expires_at: utcValue(defaultExpiresAt),
    };
    if (retryItems) {
      return {
        operation_id: operationId.current,
        decision,
        reason: decision === "reject" ? reason.trim() : null,
        ...defaultPeriod,
        selection: {
          mode: "explicit_items",
          service_date: filter.service_date ?? null,
          items: retryItems.map((item) => ({
            application_id: item.application_id,
            expected_version: item.expected_version,
          })),
        },
      };
    }
    const selectedOverrides = decisionItems(selectedSet);
    return {
      operation_id: operationId.current,
      decision,
      reason: decision === "reject" ? reason.trim() : null,
      ...defaultPeriod,
      selection: allFiltered
        ? {
            mode: "all_filtered",
            filter,
            ...(selectedOverrides.length
              ? { overrides: selectedOverrides }
              : {}),
          }
        : {
            mode: "explicit_items",
            service_date: filter.service_date ?? null,
            items: selectedOverrides,
          },
    };
  }

  async function createBatch(payload: object) {
    setError("");
    try {
      const created = await onSubmit?.(payload);
      if (created) {
        setBatch(created);
        if (onLoadItems) setResults(await onLoadItems(created.id));
      }
      operationId.current = null;
      setConfirming(false);
      setMessage("批次已建立，可在逐筆結果查看進度、衝突與失敗項目。");
      setToast(
        `已建立志工${decision === "approve" ? "核准" : "拒絕"}批次（${
          allFiltered ? matchingCount : selected.length
        } 筆）`,
      );
    } catch (error) {
      setConfirming(false);
      setError(
        error instanceof Error ? error.message : "批次建立失敗，輸入已保留",
      );
    }
  }

  async function loadBatchState(batchId: string) {
    const [latest, latestItems] = await Promise.all([
      onLoadBatch?.(batchId) ?? Promise.resolve(batch),
      onLoadItems?.(batchId) ?? Promise.resolve(results),
    ]);
    if (!latest) return;
    setBatch(latest);
    setResults(latestItems);
    if (
      isTerminalBatch(latest) &&
      shouldReloadAfterTerminalBatch(latest) &&
      terminalNotifiedBatch.current !== latest.id
    ) {
      terminalNotifiedBatch.current = latest.id;
      await onBatchTerminalSuccess?.(latest);
    }
    return latest;
  }

  React.useEffect(() => {
    if (!batch || isTerminalBatch(batch) || !onLoadBatch) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const latest = await loadBatchState(batch.id);
        if (!cancelled && latest && !isTerminalBatch(latest)) {
          timer = setTimeout(() => void poll(), 1000);
        }
      } catch {
        if (!cancelled) timer = setTimeout(() => void poll(), 1500);
      }
    };
    timer = setTimeout(() => void poll(), 500);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [batch, onLoadBatch]);

  async function submit() {
    if (!allFiltered && selected.length === 0) {
      setMessage("請至少選擇一筆申請");
      return;
    }
    if (decision === "reject" && !reason.trim()) {
      setMessage("拒絕申請時必須填寫原因");
      return;
    }
    setConfirming(true);
    setMessage(
      allFiltered
        ? `請確認：將鎖定目前篩選結果全部 ${matchingCount.toLocaleString("zh-TW")} 筆。`
        : `請確認：將處理已選取的 ${selected.length} 筆。`,
    );
  }

  async function refresh() {
    if (!batch) return;
    try {
      await loadBatchState(batch.id);
      setMessage("已更新批次進度與逐筆結果。");
    } catch {
      setMessage("無法更新批次進度，請稍後再試。");
    }
  }

  async function retryFailed() {
    const failed = results
      .filter((item) => item.result === "failed")
      .slice(0, 500);
    if (!failed.length) return;
    operationId.current = null;
    await createBatch(buildPayload(failed));
  }

  const failedCount = results.filter((item) => item.result === "failed").length;

  return (
    <section
      className="ui-card ui-card-padded volunteer-workbench"
      aria-labelledby="batch-title"
    >
      <div className="volunteer-workbench-heading">
        <div>
          <span className="eyebrow">APPLICATION QUEUE</span>
          <h2 id="batch-title">待審核申請</h2>
        </div>
        <Badge className="volunteer-application-count">
          {matchingCount.toLocaleString("zh-TW")} 筆
        </Badge>
      </div>
      <div className="volunteer-workbench-grid">
        <div className="volunteer-applicant-list">
          {loading ? (
            <div className="volunteer-workbench-state">
              <span className="loading-dot" aria-hidden="true" />
              <p role="status" aria-live="polite">
                載入申請名單中…
              </p>
            </div>
          ) : applications.length === 0 ? (
            <EmptyState
              title="目前日期沒有待審核申請"
              description="請從上方審核日期選擇其他服務日期，或調整篩選條件。"
            />
          ) : (
            <>
              <label className="volunteer-select-all">
                <Checkbox
                  checked={allFiltered}
                  onChange={(event) => {
                    setAllFiltered(event.target.checked);
                    setConfirming(false);
                  }}
                />
                <span>
                  目前篩選結果全部 {matchingCount.toLocaleString("zh-TW")} 筆
                </span>
              </label>
              <Table className="batch-table">
                <thead>
                  <tr>
                    <th className="ui-table-head">選取</th>
                    <th className="ui-table-head">志工</th>
                    <th className="ui-table-head">狀態</th>
                    <th className="ui-table-head">個別期限</th>
                    {onViewApplicant ? (
                      <th className="ui-table-head">資料</th>
                    ) : null}
                  </tr>
                </thead>
                <tbody>
                  {applications.map((application) => (
                    <tr key={application.id}>
                      <td className="ui-table-cell">
                        <Checkbox
                          aria-label={`選取 ${application.display_name}`}
                          checked={selectedSet.has(application.id)}
                          onChange={(event) => {
                            setConfirming(false);
                            setSelected((current) =>
                              event.target.checked
                                ? [...current, application.id]
                                : current.filter((id) => id !== application.id),
                            );
                          }}
                        />
                      </td>
                      <td className="ui-table-cell volunteer-applicant-name">
                        {application.display_name}
                      </td>
                      <td className="ui-table-cell">
                        <Badge className="volunteer-status-badge">
                          {application.status}
                        </Badge>
                      </td>
                      <td className="ui-table-cell">
                        <Input
                          aria-label={`${application.display_name} 個別到期時間`}
                          type="datetime-local"
                          disabled={!selectedSet.has(application.id)}
                          value={overrides[application.id] ?? ""}
                          onChange={(event) =>
                            setOverrides((current) => ({
                              ...current,
                              [application.id]: event.target.value,
                            }))
                          }
                        />
                      </td>
                      {onViewApplicant ? (
                        <td className="ui-table-cell">
                          <Button
                            type="button"
                            variant="secondary"
                            onClick={() => onViewApplicant(application.id)}
                          >
                            查看申請資料
                          </Button>
                        </td>
                      ) : null}
                    </tr>
                  ))}
                </tbody>
              </Table>
            </>
          )}
        </div>
        {applications.length > 0 ? (
          <aside
            className="volunteer-decision-panel"
            aria-labelledby="decision-panel-title"
          >
            <div className="decision-panel-heading">
              <div>
                <span className="eyebrow">BATCH ACTION</span>
                <h3 id="decision-panel-title">批次決策</h3>
              </div>
              <span className="muted">先選申請，再送出</span>
            </div>
            <div className="batch-controls">
              <label>
                決策
                <Select
                  value={decision}
                  onChange={(event) => {
                    setDecision(event.target.value as typeof decision);
                    setConfirming(false);
                  }}
                >
                  <option value="approve">核准</option>
                  <option value="reject">拒絕</option>
                </Select>
              </label>
              {decision === "reject" ? (
                <label>
                  拒絕原因
                  <Input
                    aria-label="拒絕原因"
                    value={reason}
                    maxLength={500}
                    onChange={(event) => setReason(event.target.value)}
                  />
                </label>
              ) : null}
            </div>
            <fieldset className="batch-period-fields">
              <legend>
                共同授權期限（留白則使用批次建立時的收容所政策快照）
              </legend>
              <label>
                開始時間
                <Input
                  type="datetime-local"
                  value={defaultValidFrom}
                  onChange={(event) => setDefaultValidFrom(event.target.value)}
                />
              </label>
              <label>
                到期時間
                <Input
                  type="datetime-local"
                  value={defaultExpiresAt}
                  onChange={(event) => setDefaultExpiresAt(event.target.value)}
                />
              </label>
            </fieldset>
            <Button type="button" onClick={submit}>
              確認並建立批次
            </Button>
          </aside>
        ) : null}
      </div>
      <MembershipPermissionDialog
        open={confirming}
        title="確認志工批次決策"
        identity={
          allFiltered ? "目前篩選結果" : `${selected.length} 筆志工報名`
        }
        operation={`批次${decision === "approve" ? "核准" : "拒絕"}`}
        before="待審核"
        after={decision === "approve" ? "建立核准授權" : "建立拒絕結果"}
        authorizationImpact={
          allFiltered
            ? `將鎖定目前篩選結果全部 ${matchingCount.toLocaleString("zh-TW")} 筆，不受分頁影響。`
            : `將處理已選取的 ${selected.length} 筆。`
        }
        confirmLabel="送出完整快照"
        closeLabel="關閉批次確認"
        destructive={decision === "reject"}
        onClose={() => setConfirming(false)}
        onConfirm={() => void createBatch(buildPayload())}
        confirming={false}
      />
      {error ? <Alert role="alert">{error}</Alert> : null}
      {toast ? <Toast onClose={() => setToast("")}>{toast}</Toast> : null}
      <h3 className="mt-6">逐筆結果</h3>
      {batch ? (
        <div>
          <p>
            進度 {batch.processed_count}/{batch.requested_count}；成功{" "}
            {batch.succeeded_count}、衝突 {batch.conflict_count}、失敗{" "}
            {batch.failed_count}
          </p>
          <Button variant="secondary" type="button" onClick={refresh}>
            更新進度
          </Button>
        </div>
      ) : null}
      {results.length ? (
        <ul>
          {results.map((item) => (
            <li key={item.application_id}>
              {item.application_id}：
              <Badge className={`batch-result batch-result-${item.result}`}>
                {item.result}
              </Badge>
              {item.error_code ? `（${item.error_code}）` : ""}
            </li>
          ))}
        </ul>
      ) : null}
      {failedCount ? (
        <Button variant="secondary" type="button" onClick={retryFailed}>
          只重試失敗項目（{Math.min(failedCount, 500)}）
        </Button>
      ) : null}
      <p role="status" aria-live="polite">
        {message || "批次送出後顯示成功、衝突與失敗項目，可只重試失敗項目。"}
      </p>
    </section>
  );
}
