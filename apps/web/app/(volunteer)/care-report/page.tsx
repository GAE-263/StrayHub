import { LiffFallback } from "../../../features/line-bot/LiffFallback";

export default function CareReportPage() {
  return (
    <main>
      <h1>照護回報備援介面</h1>
      <p>主要回報流程在 LINE Bot 完成；此頁供較完整修改與中斷恢復使用。</p>
      <LiffFallback />
    </main>
  );
}
