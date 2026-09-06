"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { authFetch, clearAuth, getAccessToken } from "../lib/auth";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PermissionDeniedState,
} from "../components/management/StateViews";
import { MANAGEMENT_HOME_STATE_COPY } from "../components/management/route-state";
import { statusLabel } from "../components/management/ui-status";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";

type Dashboard = {
  organization_id: string;
  role: string;
  summary: {
    reportable_animal_count: number;
    today_report_count: number;
    active_draft_count: number;
    pending_ai_count: number;
    alerts: string[];
  };
  recent_reports: Array<{
    id: string;
    animal_id: string;
    animal_name: string;
    animal_shelter_number: string | null;
    submitted_at: string;
    status: string;
    ai_job_status: string;
  }>;
};

const metrics = [
  ["reportable_animal_count", "今日可回報動物"],
  ["today_report_count", "今日已收回報"],
  ["active_draft_count", "未完成 Draft"],
  ["pending_ai_count", "待處理 AI"],
] as const;

const REPORT_STATUS_LABELS: Record<string, string> = {
  saved: "回報已送出",
  amended: "已修正回報",
};

const AI_JOB_STATUS_LABELS: Record<string, string> = {
  not_required: "不需要 AI 覆核",
  pending: "等待 AI 處理",
  pending_enqueue: "等待 AI 處理",
  enqueue_failed: "AI 派工失敗",
  retry_wait: "等待重試",
  running: "AI 處理中",
  succeeded: "AI 已完成，待覆核",
  failed: "AI 處理失敗",
  invalid: "AI 結果無效",
};

function reportStatusLabel(value: string) {
  return REPORT_STATUS_LABELS[value] ?? statusLabel(value);
}

function aiJobStatusLabel(value: string) {
  return AI_JOB_STATUS_LABELS[value] ?? statusLabel(value);
}

export default function ManagementHome() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [permissionDenied, setPermissionDenied] = useState(false);

  useEffect(() => {
    if (!getAccessToken()) return;
    let cancelled = false;
    void authFetch("/v1/management/dashboard")
      .then(async (response) => {
        if (response.status === 401) {
          clearAuth();
          window.location.assign("/login");
          return;
        }
        if (response.status === 403) {
          setPermissionDenied(true);
          return;
        }
        if (!response.ok)
          throw new Error(`無法載入 Dashboard（HTTP ${response.status}）`);
        const data = (await response.json()) as Dashboard;
        if (!cancelled) setDashboard(data);
      })
      .catch((requestError: unknown) => {
        if (!cancelled)
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Dashboard 載入失敗",
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section aria-labelledby="management-home-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">TODAY AT A GLANCE</span>
          <h1 id="management-home-title">管理工作台總覽</h1>
          <p>從今日照護狀態開始，快速找到動物、回報與待處理任務。</p>
        </div>
        <Link className="ui-button ui-button-default" href="/animals">
          查看動物清單
        </Link>
      </div>
      {loading ? <LoadingState title="正在載入今日摘要…" /> : null}
      {permissionDenied ? (
        <PermissionDeniedState
          description={MANAGEMENT_HOME_STATE_COPY.permissionDenied.nextStep}
        />
      ) : null}
      {error ? (
        <ErrorState title="Dashboard 載入失敗" description={error} />
      ) : null}
      {dashboard ? (
        <>
          <div className="metric-grid">
            {metrics.map(([key, label]) => (
              <Card className="metric-card" key={key}>
                <span>{label}</span>
                <strong>{dashboard.summary[key]}</strong>
              </Card>
            ))}
          </div>
          <div className="content-grid">
            <Card
              className="ui-card-padded"
              aria-labelledby="recent-reports-title"
            >
              <div className="panel-heading">
                <h2 id="recent-reports-title">最近回報</h2>
                <Link className="text-link" href="/reports">
                  開啟回報收件匣 →
                </Link>
              </div>
              {dashboard.recent_reports.length === 0 ? (
                <EmptyState
                  title={MANAGEMENT_HOME_STATE_COPY.emptyRecentReports.label}
                  description={
                    MANAGEMENT_HOME_STATE_COPY.emptyRecentReports.nextStep
                  }
                />
              ) : (
                <div className="recent-reports-table">
                  <div className="recent-report-row recent-report-header">
                    <span>動物</span>
                    <span>回報狀態</span>
                    <span>AI 處理</span>
                    <span>提交時間</span>
                  </div>
                  <ul className="recent-reports-list">
                    {dashboard.recent_reports.map((report) => (
                      <li key={report.id}>
                        <Link
                          className="recent-report-row"
                          href={`/animals/${report.animal_id}`}
                        >
                          <div className="recent-report-animal">
                            <strong>{report.animal_name}</strong>
                            {report.animal_shelter_number ? (
                              <span className="recent-report-shelter-no">
                                {report.animal_shelter_number}
                              </span>
                            ) : null}
                          </div>
                          <div className="recent-report-badges">
                            <Badge>{reportStatusLabel(report.status)}</Badge>
                          </div>
                          <div className="recent-report-badges">
                            <Badge>{aiJobStatusLabel(report.ai_job_status)}</Badge>
                          </div>
                          <span className="recent-report-time muted">
                            {new Date(report.submitted_at).toLocaleString(
                              "zh-TW",
                            )}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
            <Card
              className="ui-card-padded"
              aria-labelledby="quick-entry-title"
            >
              <h2 id="quick-entry-title">快速入口</h2>
              <Link className="link-card" href="/animals">
                <strong>動物檔案</strong>
                <p className="muted">搜尋收容編號、Cage／Area 與最近活動。</p>
              </Link>
              <Link className="link-card" href="/reports">
                <strong>回報收件匣</strong>
                <p className="muted">依日期、動物與狀態處理照護回報。</p>
              </Link>
              <Link className="link-card" href="/ai-review">
                <strong>AI 人工覆核</strong>
                <p className="muted">人工確認、拒絕或修正 AI 結果。</p>
              </Link>
            </Card>
          </div>
        </>
      ) : null}
    </section>
  );
}
