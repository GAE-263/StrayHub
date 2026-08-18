"use client";

import React, { useMemo, useRef, useState } from "react";

import { MembershipPermissionDialog } from "../../components/management/MembershipPermissionDialog";
import { Toast } from "../../components/ui/toast";

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
  id: string;
  application_id: string;
  expected_version: number;
  result: string;
  error_code?: string | null;
};

function utcValue(localValue: string): string | null {
  if (!localValue) return null;
  const parsed = new Date(localValue);
  return Number.isNaN(parsed.valueOf()) ? null : parsed.toISOString();
}

export function ApplicationBatchWorkbench({
  applications,
  matchingCount,
  filter = { status: "pending" },
  onSubmit,
  onLoadItems,
  onLoadBatch,
}: {
  applications: Application[];
  matchingCount: number;
  filter?: {
    status: "pending";
    submitted_from?: string;
    submitted_to?: string;
  };
  onSubmit?: (payload: object) => Promise<Batch | void> | Batch | void;
  onLoadItems?: (batchId: string) => Promise<BatchItem[]>;
  onLoadBatch?: (batchId: string) => Promise<Batch>;
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
        : { mode: "explicit_items", items: selectedOverrides },
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
      const [latest, latestItems] = await Promise.all([
        onLoadBatch?.(batch.id) ?? Promise.resolve(batch),
        onLoadItems?.(batch.id) ?? Promise.resolve(results),
      ]);
      setBatch(latest);
      setResults(latestItems);
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
    <section className="panel ui-card" aria-labelledby="batch-title">
      <h2 id="batch-title">志工報名審核</h2>
      <div className="mt-4 flex flex-wrap gap-4">
        <label>
          <input
            type="checkbox"
            checked={allFiltered}
            onChange={(event) => {
              setAllFiltered(event.target.checked);
              setConfirming(false);
            }}
          />{" "}
          目前篩選結果全部 {matchingCount.toLocaleString("zh-TW")} 筆
        </label>
        <label>
          決策
          <select
            value={decision}
            onChange={(event) => {
              setDecision(event.target.value as typeof decision);
              setConfirming(false);
            }}
          >
            <option value="approve">核准</option>
            <option value="reject">拒絕</option>
          </select>
        </label>
        {decision === "reject" ? (
          <label>
            拒絕原因
            <input
              aria-label="拒絕原因"
              value={reason}
              maxLength={500}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
        ) : null}
      </div>
      <fieldset className="mt-4 flex flex-wrap gap-4">
        <legend>共同授權期限（留白則使用批次建立時的收容所政策快照）</legend>
        <label>
          開始時間
          <input
            type="datetime-local"
            value={defaultValidFrom}
            onChange={(event) => setDefaultValidFrom(event.target.value)}
          />
        </label>
        <label>
          到期時間
          <input
            type="datetime-local"
            value={defaultExpiresAt}
            onChange={(event) => setDefaultExpiresAt(event.target.value)}
          />
        </label>
      </fieldset>
      <div className="mt-5 overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th>選取</th>
              <th>志工</th>
              <th>狀態</th>
              <th>個別期限</th>
            </tr>
          </thead>
          <tbody>
            {applications.map((application) => (
              <tr key={application.id}>
                <td>
                  <input
                    aria-label={`選取 ${application.display_name}`}
                    type="checkbox"
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
                <td>{application.display_name}</td>
                <td>{application.status}</td>
                <td>
                  <input
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
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        onClick={submit}
        className="mt-5 min-h-11 rounded-lg bg-emerald-700 px-5 text-white"
      >
        確認並建立批次
      </button>
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
        onClose={() => setConfirming(false)}
        onConfirm={() => void createBatch(buildPayload())}
        confirming={false}
      />
      {error ? <p role="alert">{error}</p> : null}
      {toast ? <Toast>{toast}</Toast> : null}
      <h3 className="mt-6">逐筆結果</h3>
      {batch ? (
        <div>
          <p>
            進度 {batch.processed_count}/{batch.requested_count}；成功{" "}
            {batch.succeeded_count}、衝突 {batch.conflict_count}、失敗{" "}
            {batch.failed_count}
          </p>
          <button type="button" onClick={refresh}>
            更新進度
          </button>
        </div>
      ) : null}
      {results.length ? (
        <ul>
          {results.map((item) => (
            <li key={item.id}>
              {item.application_id}：{item.result}
              {item.error_code ? `（${item.error_code}）` : ""}
            </li>
          ))}
        </ul>
      ) : null}
      {failedCount ? (
        <button type="button" onClick={retryFailed}>
          只重試失敗項目（{Math.min(failedCount, 500)}）
        </button>
      ) : null}
      <p role="status" aria-live="polite">
        {message || "批次送出後顯示成功、衝突與失敗項目，可只重試失敗項目。"}
      </p>
    </section>
  );
}
