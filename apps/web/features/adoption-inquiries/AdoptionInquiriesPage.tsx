"use client";

import { ClipboardList, Phone } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PermissionDeniedState,
} from "../../components/management/StateViews";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Dialog } from "../../components/ui/dialog";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Table } from "../../components/ui/table";
import {
  AdoptionInquiryApiError,
  fetchAdoptionInquiries,
  updateAdoptionInquiryStatus,
} from "./api";
import type {
  AdoptionInquiry,
  AdoptionInquiryListResponse,
  InquiryStatus,
} from "./types";
import styles from "./adoption-inquiries.module.css";

const PATH_LABEL = {
  specific_animal: "心有所屬",
  recommend_me: "推薦名單",
} as const;

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function StatusBadge({ status }: { status: InquiryStatus }) {
  return (
    <Badge
      className={status === "new" ? styles.newBadge : styles.contactedBadge}
    >
      {status === "new" ? "待聯繫" : "已聯繫"}
    </Badge>
  );
}

export function AdoptionInquiriesPage() {
  const [draftSearch, setDraftSearch] = useState("");
  const [search, setSearch] = useState("");
  const [path, setPath] = useState("");
  const [status, setStatus] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<AdoptionInquiryListResponse | null>(null);
  const [viewing, setViewing] = useState<AdoptionInquiry | null>(null);
  const [loadState, setLoadState] = useState<
    "loading" | "ready" | "error" | "permission"
  >("loading");
  const [actionError, setActionError] = useState("");
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const clearFilters = useCallback(() => {
    setDraftSearch("");
    setSearch("");
    setPath("");
    setStatus("");
    setFromDate("");
    setToDate("");
    setPage(1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoadState("loading");
    setActionError("");
    void fetchAdoptionInquiries(
      { page, search, path, status, fromDate, toDate },
      controller.signal,
    )
      .then((response) => {
        if (controller.signal.aborted) return;
        setData(response);
        setLoadState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setData(null);
        setLoadState(
          error instanceof AdoptionInquiryApiError && error.status === 403
            ? "permission"
            : "error",
        );
      });
    return () => controller.abort();
  }, [fromDate, page, path, reloadToken, search, status, toDate]);

  async function toggleStatus(inquiry: AdoptionInquiry) {
    const nextStatus: InquiryStatus =
      inquiry.status === "new" ? "contacted" : "new";
    setUpdatingId(inquiry.id);
    setActionError("");
    try {
      const updated = await updateAdoptionInquiryStatus(inquiry.id, nextStatus);
      setData((current) =>
        current
          ? {
              ...current,
              items: current.items.map((item) =>
                item.id === updated.id ? updated : item,
              ),
            }
          : current,
      );
    } catch {
      setActionError("狀態未更新。請確認連線後再試一次。資料仍維持原狀。");
    } finally {
      setUpdatingId(null);
    }
  }

  const hasFilters = Boolean(search || path || status || fromDate || toDate);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>領養流程追蹤</p>
          <h1>領養意願</h1>
          <p>集中查看 LINE 問卷、適配資訊與聯繫進度。</p>
        </div>
        <span className={styles.headerMark} aria-hidden="true">
          <ClipboardList size={24} />
        </span>
      </header>

      {loadState === "permission" ? null : (
        <form
          className={styles.filters}
          aria-label="搜尋與篩選領養意願"
          onSubmit={(event) => {
            event.preventDefault();
            setSearch(draftSearch.trim());
            setPage(1);
          }}
        >
          <Field className={styles.searchField}>
            <label htmlFor="inquiry-search">搜尋</label>
            <Input
              id="inquiry-search"
              type="search"
              maxLength={120}
              value={draftSearch}
              placeholder="毛孩、收容編號、領養人或電話"
              onChange={(event) => setDraftSearch(event.target.value)}
            />
          </Field>
          <Field>
            <label htmlFor="inquiry-path">領養方式</label>
            <Select
              id="inquiry-path"
              value={path}
              onChange={(event) => {
                setPath(event.target.value);
                setPage(1);
              }}
            >
              <option value="">全部方式</option>
              <option value="specific_animal">心有所屬</option>
              <option value="recommend_me">推薦名單</option>
            </Select>
          </Field>
          <Field>
            <label htmlFor="inquiry-status">聯繫狀態</label>
            <Select
              id="inquiry-status"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setPage(1);
              }}
            >
              <option value="">全部狀態</option>
              <option value="new">待聯繫</option>
              <option value="contacted">已聯繫</option>
            </Select>
          </Field>
          <Field>
            <label htmlFor="inquiry-from">開始日期</label>
            <Input
              id="inquiry-from"
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
            <label htmlFor="inquiry-to">結束日期</label>
            <Input
              id="inquiry-to"
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
            {hasFilters ? (
              <Button type="button" variant="ghost" onClick={clearFilters}>
                清除條件
              </Button>
            ) : null}
          </div>
        </form>
      )}

      {actionError ? (
        <p className={styles.actionError} role="alert">
          {actionError}
        </p>
      ) : null}
      {loadState === "loading" ? (
        <LoadingState
          title="正在整理領養意願"
          description="正在取得目前收容所的資料。"
        />
      ) : loadState === "permission" ? (
        <PermissionDeniedState description="請切換到已授權收容所，或聯絡收容所管理者。" />
      ) : loadState === "error" ? (
        <ErrorState
          title="目前無法載入領養意願"
          description="請確認連線後再試一次；畫面不會保留其他收容所的資料。"
          action={
            <Button onClick={() => setReloadToken((value) => value + 1)}>
              重新載入
            </Button>
          }
        />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title={hasFilters ? "找不到符合條件的領養意願" : "目前還沒有領養意願"}
          description={
            hasFilters
              ? "請調整搜尋或篩選條件。"
              : "LINE 問卷送出後會顯示在這裡。"
          }
          action={
            hasFilters ? (
              <Button variant="ghost" onClick={clearFilters}>
                清除條件
              </Button>
            ) : undefined
          }
        />
      ) : (
        <InquiryResults
          data={data}
          updatingId={updatingId}
          onView={setViewing}
          onToggle={(item) => void toggleStatus(item)}
          onPrevious={() => setPage((value) => Math.max(1, value - 1))}
          onNext={() => setPage((value) => value + 1)}
        />
      )}

      <Dialog
        open={viewing !== null}
        title={viewing ? `${viewing.animal_name}的領養問卷` : "領養問卷"}
        onClose={() => setViewing(null)}
      >
        {viewing ? (
          <div className={styles.answerList}>
            {viewing.answers_display.map((answer) => (
              <div key={answer.key}>
                <span>{answer.label}</span>
                <strong>{answer.value}</strong>
              </div>
            ))}
            {viewing.ai_suitability_explanation ? (
              <p className={styles.aiNote}>
                <strong>AI 適配說明</strong>
                {viewing.ai_suitability_explanation}
              </p>
            ) : null}
          </div>
        ) : null}
      </Dialog>
    </div>
  );
}

function InquiryResults({
  data,
  updatingId,
  onView,
  onToggle,
  onPrevious,
  onNext,
}: {
  data: AdoptionInquiryListResponse;
  updatingId: string | null;
  onView: (item: AdoptionInquiry) => void;
  onToggle: (item: AdoptionInquiry) => void;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <section aria-label="領養意願清單">
      <p className={styles.resultCount}>共 {data.total} 筆領養意願</p>
      <div className={styles.desktopTable}>
        <Table>
          <thead>
            <tr>
              <th>送出時間</th>
              <th>毛孩</th>
              <th>領養人</th>
              <th>方式</th>
              <th>AI 適配度</th>
              <th>狀態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((item) => (
              <tr key={item.id}>
                <td>{formatTimestamp(item.submitted_at)}</td>
                <td>
                  <strong>{item.animal_name}</strong>
                  <br />
                  <span className={styles.muted}>
                    {item.shelter_number ?? "未提供編號"}
                  </span>
                </td>
                <td>
                  {item.adopter_name}
                  <br />
                  <span className={styles.muted}>{item.phone_number}</span>
                </td>
                <td>
                  <Badge>{PATH_LABEL[item.path]}</Badge>
                  {item.ai_recommendation_overridden ? (
                    <Badge className={styles.overrideBadge}>非推薦選擇</Badge>
                  ) : null}
                </td>
                <td>
                  {item.ai_suitability_score === null
                    ? "—"
                    : `${item.ai_suitability_score}/100`}
                </td>
                <td>
                  <StatusBadge status={item.status} />
                </td>
                <td>
                  <InquiryActions
                    item={item}
                    updating={updatingId === item.id}
                    onView={onView}
                    onToggle={onToggle}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
      <div className={styles.mobileList}>
        {data.items.map((item) => (
          <Card className={styles.mobileCard} key={item.id}>
            <div className={styles.cardHeading}>
              <div>
                <h2>{item.animal_name}</h2>
                <p>{item.shelter_number ?? "未提供收容編號"}</p>
              </div>
              <StatusBadge status={item.status} />
            </div>
            <dl>
              <div>
                <dt>領養人</dt>
                <dd>{item.adopter_name}</dd>
              </div>
              <div>
                <dt>送出時間</dt>
                <dd>{formatTimestamp(item.submitted_at)}</dd>
              </div>
              <div>
                <dt>領養方式</dt>
                <dd>{PATH_LABEL[item.path]}</dd>
              </div>
            </dl>
            <a className={styles.phoneLink} href={`tel:${item.phone_number}`}>
              <Phone size={16} aria-hidden="true" />
              {item.phone_number}
            </a>
            <InquiryActions
              item={item}
              updating={updatingId === item.id}
              onView={onView}
              onToggle={onToggle}
            />
          </Card>
        ))}
      </div>
      {data.total > data.page_size ? (
        <nav className={styles.pagination} aria-label="領養意願分頁">
          <Button
            variant="ghost"
            disabled={data.page <= 1}
            onClick={onPrevious}
          >
            上一頁
          </Button>
          <span>
            第 {data.page} / {Math.ceil(data.total / data.page_size)} 頁
          </span>
          <Button
            variant="ghost"
            disabled={data.page * data.page_size >= data.total}
            onClick={onNext}
          >
            下一頁
          </Button>
        </nav>
      ) : null}
    </section>
  );
}

function InquiryActions({
  item,
  updating,
  onView,
  onToggle,
}: {
  item: AdoptionInquiry;
  updating: boolean;
  onView: (item: AdoptionInquiry) => void;
  onToggle: (item: AdoptionInquiry) => void;
}) {
  return (
    <div className={styles.rowActions}>
      <Button variant="ghost" onClick={() => onView(item)}>
        查看問卷
      </Button>
      <Button
        variant="secondary"
        disabled={updating}
        onClick={() => onToggle(item)}
      >
        {updating
          ? "更新中…"
          : item.status === "new"
            ? "標記已聯繫"
            : "標記待聯繫"}
      </Button>
    </div>
  );
}
