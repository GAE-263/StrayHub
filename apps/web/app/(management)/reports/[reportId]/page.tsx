"use client";
import { use } from "react";
import { ReportDetail } from "../../../../features/report-inbox/ReportInbox";
export default function ReportDetailPage({
  params,
}: {
  params: Promise<{ reportId: string }>;
}) {
  const { reportId } = use(params);
  return <ReportDetail id={reportId} />;
}
