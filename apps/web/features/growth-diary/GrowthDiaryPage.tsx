"use client";

import React, { useCallback, useEffect, useState } from "react";
import { HeartHandshake } from "lucide-react";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PermissionDeniedState,
} from "../../components/management/StateViews";
import { Button } from "../../components/ui/button";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { fetchGrowthDiaryEntries, GrowthDiaryApiError } from "./api";
import { GrowthDiaryEntryCard } from "./GrowthDiaryEntryCard";
import type {
  GrowthDiaryListResponse,
  GrowthDiaryMoodFilter,
  GrowthDiaryStatusFilter,
} from "./types";
import styles from "./growth-diary.module.css";

export type GrowthDiaryViewState = "loading" | "ready" | "error" | "permission";

export function GrowthDiaryPageView({
  state,
  data,
  onRetry,
  controls,
  hasActiveFilters = false,
  onClearFilters,
  onPreviousPage,
  onNextPage,
}: {
  state: GrowthDiaryViewState;
  data: GrowthDiaryListResponse | null;
  onRetry?: () => void;
  controls?: React.ReactNode;
  hasActiveFilters?: boolean;
  onClearFilters?: () => void;
  onPreviousPage?: () => void;
  onNextPage?: () => void;
}) {
  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <p className={styles.eyebrow}>返家後生活札記</p>
        <div className={styles.titleRow}>
          <div>
            <h1>毛孩日記</h1>
            <p>查看領養人分享的近況，原始內容與 AI 輔助資訊會分開呈現。</p>
          </div>
          <span className={styles.headerMark} aria-hidden="true">
            <HeartHandshake size={24} />
          </span>
        </div>
      </header>

      {state === "permission" ? null : controls}

      {state === "loading" ? (
        <LoadingState
          title="正在整理毛孩日記"
          description="正在取得目前收容所的最新分享。"
        />
      ) : state === "permission" ? (
        <PermissionDeniedState
          title="沒有查看毛孩日記的權限"
          description="請確認目前收容所與管理角色；此頁不會顯示其他收容所的資料。"
        />
      ) : state === "error" ? (
        <ErrorState
          title="目前無法載入毛孩日記"
          description="請確認連線後再試一次；畫面不會保留其他收容所的資料。"
          action={
            onRetry ? <Button onClick={onRetry}>重新載入</Button> : undefined
          }
        />
      ) : (!data || data.items.length === 0) && hasActiveFilters ? (
        <EmptyState
          title="找不到符合條件的日記"
          description="請調整搜尋文字或關注狀態，再查看目前收容所的日記。"
          action={
            onClearFilters ? (
              <Button type="button" variant="ghost" onClick={onClearFilters}>
                清除搜尋與篩選
              </Button>
            ) : undefined
          }
        />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="還沒有毛孩日記"
          description="領養人分享近況後，日記會依時間出現在這裡。"
        />
      ) : (
        <section aria-label="毛孩日記時間軸">
          <p className={styles.resultCount}>共 {data.total} 筆日記</p>
          <div className={styles.timeline}>
            {data.items.map((entry) => (
              <GrowthDiaryEntryCard key={entry.id} entry={entry} />
            ))}
          </div>
          {data.total > data.page_size ? (
            <nav className={styles.pagination} aria-label="毛孩日記分頁">
              <Button
                type="button"
                variant="ghost"
                disabled={data.page <= 1}
                onClick={onPreviousPage}
              >
                上一頁
              </Button>
              <span>
                第 {data.page} / {Math.ceil(data.total / data.page_size)} 頁
              </span>
              <Button
                type="button"
                variant="ghost"
                disabled={data.page * data.page_size >= data.total}
                onClick={onNextPage}
              >
                下一頁
              </Button>
            </nav>
          ) : null}
        </section>
      )}
    </div>
  );
}

export function GrowthDiaryPage() {
  const [state, setState] = useState<GrowthDiaryViewState>("loading");
  const [data, setData] = useState<GrowthDiaryListResponse | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [draftQuery, setDraftQuery] = useState("");
  const [query, setQuery] = useState("");
  const [mood, setMood] = useState<GrowthDiaryMoodFilter>("all");
  const [status, setStatus] = useState<GrowthDiaryStatusFilter>("all");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const retry = useCallback(() => setReloadToken((value) => value + 1), []);

  const clearFilters = useCallback(() => {
    setDraftQuery("");
    setQuery("");
    setMood("all");
    setStatus("all");
    setFromDate("");
    setToDate("");
    setPage(1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    setData(null);
    void fetchGrowthDiaryEntries(
      { query, mood, status, fromDate, toDate, page, pageSize },
      controller.signal,
    )
      .then((response) => {
        if (controller.signal.aborted) return;
        setData(response);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setData(null);
        setState(
          error instanceof GrowthDiaryApiError && error.status === 403
            ? "permission"
            : "error",
        );
      });
    return () => controller.abort();
  }, [fromDate, mood, page, query, reloadToken, status, toDate]);

  const controls = (
    <form
      className={styles.filters}
      aria-label="搜尋與篩選毛孩日記"
      onSubmit={(event) => {
        event.preventDefault();
        setQuery(draftQuery.trim());
        setPage(1);
      }}
    >
      <Field className={styles.searchField}>
        <label htmlFor="growth-diary-query">動物名稱或收容編號</label>
        <Input
          id="growth-diary-query"
          type="search"
          maxLength={120}
          value={draftQuery}
          placeholder="例如：米糕、A-102"
          onChange={(event) => setDraftQuery(event.target.value)}
        />
      </Field>
      <Field>
        <label htmlFor="growth-diary-mood">關注狀態</label>
        <Select
          id="growth-diary-mood"
          value={mood}
          onChange={(event) => {
            setMood(event.target.value as GrowthDiaryMoodFilter);
            setPage(1);
          }}
        >
          <option value="all">全部日記</option>
          <option value="concern">AI 建議人工查看</option>
          <option value="positive">正向近況</option>
          <option value="neutral">一般近況</option>
          <option value="unanalyzed">尚無有效分析</option>
        </Select>
      </Field>
      <Field>
        <label htmlFor="growth-diary-status">查看狀態</label>
        <Select
          id="growth-diary-status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as GrowthDiaryStatusFilter);
            setPage(1);
          }}
        >
          <option value="all">全部狀態</option>
          <option value="new">待查看</option>
          <option value="reviewed">已查看</option>
        </Select>
      </Field>
      <Field>
        <label htmlFor="growth-diary-from">開始日期</label>
        <Input
          id="growth-diary-from"
          type="date"
          value={fromDate}
          max={toDate || undefined}
          onChange={(event) => {
            setFromDate(event.target.value);
            setPage(1);
          }}
        />
      </Field>
      <Field>
        <label htmlFor="growth-diary-to">結束日期</label>
        <Input
          id="growth-diary-to"
          type="date"
          value={toDate}
          min={fromDate || undefined}
          onChange={(event) => {
            setToDate(event.target.value);
            setPage(1);
          }}
        />
      </Field>
      <div className={styles.filterActions}>
        <Button type="submit">搜尋</Button>
        {query || mood !== "all" || status !== "all" || fromDate || toDate ? (
          <Button type="button" variant="ghost" onClick={clearFilters}>
            清除條件
          </Button>
        ) : null}
      </div>
    </form>
  );

  return (
    <GrowthDiaryPageView
      state={state}
      data={data}
      onRetry={retry}
      controls={controls}
      hasActiveFilters={Boolean(
        query || mood !== "all" || status !== "all" || fromDate || toDate,
      )}
      onClearFilters={clearFilters}
      onPreviousPage={() => setPage((value) => Math.max(1, value - 1))}
      onNextPage={() => setPage((value) => value + 1)}
    />
  );
}
