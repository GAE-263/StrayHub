"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ManagementLayout } from "../components/management/ManagementLayout";
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
import { Table } from "../components/ui/table";

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
    <ManagementLayout>
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
                  <Table>
                    <thead>
                      <tr>
                        <th>提交時間</th>
                        <th>Animal ID</th>
                        <th>狀態</th>
                        <th>AI</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.recent_reports.map((report) => (
                        <tr key={report.id}>
                          <td>
                            {new Date(report.submitted_at).toLocaleString(
                              "zh-TW",
                            )}
                          </td>
                          <td>
                            <Link
                              className="text-link"
                              href={`/animals/${report.animal_id}`}
                            >
                              {report.animal_id.slice(0, 8)}…
                            </Link>
                          </td>
                          <td>
                            <Badge>{statusLabel(report.status)}</Badge>
                          </td>
                          <td>{statusLabel(report.ai_job_status)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
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
    </ManagementLayout>
  );
}
