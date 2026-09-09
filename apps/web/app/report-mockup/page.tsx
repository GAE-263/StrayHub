"use client";

import { useMemo, useState } from "react";
import styles from "./page.module.css";

type Attention = "urgent" | "review" | "normal";
type ReviewStatus = "pending" | "acknowledged" | "follow_up";

type MockReport = {
  id: string;
  animal: string;
  number: string;
  volunteer: string;
  time: string;
  attention: Attention;
  status: ReviewStatus;
  summary: string;
  note: string;
  signals: string[];
  uncertainty?: string;
  followUp?: string;
  answers: [string, string][];
  media: number;
};

const reports: MockReport[] = [
  {
    id: "r-001",
    animal: "小黑",
    number: "A023",
    volunteer: "王小姐",
    time: "今天 16:20",
    attention: "urgent",
    status: "pending",
    summary: "右後腳偶爾不敢踩地，走路狀況明顯異常。",
    note: "今天走到一半發現小黑右後腳偶爾不太敢踩地，停下來舔腳掌，後來就先帶回去了。",
    signals: ["明顯不對", "散步走一半", "停下舔腳掌"],
    uncertainty: "是否為暫時性不適，尚未確認。",
    followUp: "請先查看右後腳，必要時通知照護負責人。",
    answers: [
      ["散步完成", "走一半"],
      ["活動狀況", "比平常差"],
      ["走路狀況", "明顯不對"],
      ["外觀／特殊狀態", "其他"],
    ],
    media: 1,
  },
  {
    id: "r-002",
    animal: "阿福",
    number: "B108",
    volunteer: "陳先生",
    time: "今天 15:48",
    attention: "review",
    status: "pending",
    summary: "活動量比平常低，散步途中多次停下並提早結束。",
    note: "剛開始有走，走到一半一直停下來，回籠後有喝水。今天很熱，不確定是不是天氣的關係。",
    signals: ["活動比平常差", "散步走一半", "多次停下"],
    uncertainty: "停下原因未確認，志工推測可能與天氣有關。",
    followUp: "可於下一次散步時留意活動量與飲水情況。",
    answers: [
      ["散步完成", "走一半"],
      ["活動狀況", "比平常差"],
      ["走路狀況", "正常"],
      ["外觀／特殊狀態", "沒發現異狀"],
    ],
    media: 0,
  },
  {
    id: "r-003",
    animal: "花花",
    number: "C041",
    volunteer: "林小姐",
    time: "今天 14:12",
    attention: "review",
    status: "follow_up",
    summary: "排便偏軟，已附上一張便便照片。",
    note: "便便比平常軟一點，精神還可以，吃完零食很開心。",
    signals: ["排便偏軟", "已附便便照片"],
    uncertainty: "僅依本次回報，無法判斷是否為持續情況。",
    followUp: "請和前幾次排便紀錄一起查看。",
    answers: [
      ["散步完成", "有走完"],
      ["活動狀況", "跟平常一樣"],
      ["排便狀況", "偏軟"],
      ["遇到其他動物", "沒遇到"],
    ],
    media: 1,
  },
  {
    id: "r-004",
    animal: "小花",
    number: "A017",
    volunteer: "趙小姐",
    time: "今天 11:05",
    attention: "normal",
    status: "acknowledged",
    summary: "本次散步與平常相近，未提到特殊狀況。",
    note: "今天有走完，沿路都很穩定。回來後有喝水。",
    signals: ["有走完", "活動跟平常一樣", "未發現異狀"],
    answers: [
      ["散步完成", "有走完"],
      ["活動狀況", "跟平常一樣"],
      ["走路狀況", "正常"],
      ["外觀／特殊狀態", "沒發現異狀"],
    ],
    media: 0,
  },
];

const attentionLabel: Record<Attention, string> = {
  urgent: "建議優先查看",
  review: "值得留意",
  normal: "一般紀錄",
};
const statusLabel: Record<ReviewStatus, string> = {
  pending: "待確認",
  acknowledged: "已確認",
  follow_up: "需追蹤",
};

export default function ReportMockupPage() {
  const [selectedId, setSelectedId] = useState(reports[0].id);
  const [filter, setFilter] = useState<"all" | Attention>("all");
  const [localStatuses, setLocalStatuses] = useState<
    Record<string, ReviewStatus>
  >({});
  const selected =
    reports.find((report) => report.id === selectedId) ?? reports[0];
  const filtered = useMemo(
    () =>
      filter === "all"
        ? reports
        : reports.filter((report) => report.attention === filter),
    [filter],
  );
  const selectedStatus = localStatuses[selected.id] ?? selected.status;

  const setStatus = (status: ReviewStatus) =>
    setLocalStatuses((current) => ({ ...current, [selected.id]: status }));

  return (
    <main className={styles.page}>
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <span className={styles.mark}>🐾</span>
          <div>
            <strong>浪浪森友會</strong>
            <span>照護管理工作台</span>
          </div>
        </div>
        <div className={styles.context}>
          目前收容所　<strong>台北南港收容所</strong>
          <span className={styles.user}>管理員 林小姐</span>
        </div>
      </header>
      <div className={styles.shell}>
        <aside className={styles.sidebar}>
          <p className={styles.overline}>今日工作</p>
          <div className={styles.navActive}>
            回報收件匣 <b>3</b>
          </div>
          <div>動物名冊</div>
          <div>照護排程</div>
          <div>志工管理</div>
          <div>設定</div>
          <div className={styles.sidebarNote}>
            <span>AI 初步整理</span>
            <p>只幫你找出值得看的回報，最後由工作人員確認。</p>
          </div>
        </aside>
        <section className={styles.content}>
          <div className={styles.heading}>
            <div>
              <p className={styles.overline}>REPORT INBOX · MOCKUP</p>
              <h1>今天的照護回報</h1>
              <p className={styles.lede}>
                先看需要你留意的狀況，再回到完整原文確認。
              </p>
            </div>
            <div className={styles.date}>
              2026 年 9 月 6 日<br />
              <span>共 {reports.length} 筆回報</span>
            </div>
          </div>
          <div className={styles.metrics}>
            <div>
              <span>待確認</span>
              <strong>2</strong>
              <small>需要先看一眼</small>
            </div>
            <div>
              <span>需追蹤</span>
              <strong>1</strong>
              <small>交給下一班接續</small>
            </div>
            <div>
              <span>一般紀錄</span>
              <strong>1</strong>
              <small>已完成查看</small>
            </div>
          </div>
          <div className={styles.toolbar}>
            <div className={styles.filters}>
              <button
                className={filter === "all" ? styles.filterActive : ""}
                onClick={() => setFilter("all")}
              >
                全部 <em>4</em>
              </button>
              <button
                className={filter === "urgent" ? styles.filterActive : ""}
                onClick={() => setFilter("urgent")}
              >
                建議優先查看 <em>1</em>
              </button>
              <button
                className={filter === "review" ? styles.filterActive : ""}
                onClick={() => setFilter("review")}
              >
                值得留意 <em>2</em>
              </button>
              <button
                className={filter === "normal" ? styles.filterActive : ""}
                onClick={() => setFilter("normal")}
              >
                一般紀錄 <em>1</em>
              </button>
            </div>
            <label className={styles.search}>
              ⌕　搜尋動物或收容編號
              <input aria-label="搜尋" placeholder="例如 A023" />
            </label>
          </div>
          <div className={styles.workspace}>
            <div className={styles.list}>
              {filtered.map((report) => {
                const currentStatus = localStatuses[report.id] ?? report.status;
                return (
                  <button
                    key={report.id}
                    className={`${styles.reportCard} ${selected.id === report.id ? styles.reportSelected : ""}`}
                    onClick={() => setSelectedId(report.id)}
                  >
                    <div className={styles.cardTop}>
                      <span
                        className={`${styles.dot} ${styles[report.attention]}`}
                      />{" "}
                      <span className={styles.attention}>
                        {attentionLabel[report.attention]}
                      </span>
                      <span className={styles.status}>
                        {statusLabel[currentStatus]}
                      </span>
                    </div>
                    <h2>
                      {report.animal} <small>{report.number}</small>
                    </h2>
                    <p>{report.summary}</p>
                    <footer>
                      {report.volunteer} · {report.time}
                      {report.media ? <span>　📎 {report.media}</span> : null}
                    </footer>
                  </button>
                );
              })}
            </div>
            <article className={styles.detail}>
              <div className={styles.detailHead}>
                <div>
                  <p className={styles.overline}>
                    AI 初步整理 · {selected.time}
                  </p>
                  <h2>
                    {selected.animal} <span>{selected.number}</span>
                  </h2>
                </div>
                <span
                  className={`${styles.pill} ${styles[selected.attention]}`}
                >
                  {attentionLabel[selected.attention]}
                </span>
              </div>
              <div className={styles.summary}>
                <span>AI 摘要</span>
                <p>{selected.summary}</p>
                <small>這是初步整理，請以原始回報與現場查看為準。</small>
              </div>
              <div className={styles.detailGrid}>
                <section>
                  <h3>為什麼提醒</h3>
                  <div className={styles.signalList}>
                    {selected.signals.map((signal) => (
                      <span key={signal}>✓　{signal}</span>
                    ))}
                  </div>
                  <h3>還不確定</h3>
                  <p className={styles.muted}>
                    {selected.uncertainty ?? "目前沒有需要補充確認的地方。"}
                  </p>
                </section>
                <section>
                  <h3>建議下一步</h3>
                  <p className={styles.nextStep}>
                    {selected.followUp ?? "目前不需要特別處理。"}
                  </p>
                  <div className={styles.answerPreview}>
                    <h3>固定回報</h3>
                    {selected.answers.map(([label, value]) => (
                      <div key={label}>
                        <span>{label}</span>
                        <strong>{value}</strong>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
              <div className={styles.original}>
                <div>
                  <h3>志工補充說明</h3>
                  <p>「{selected.note}」</p>
                  <span>
                    {selected.volunteer} 提交 ·{" "}
                    {selected.media
                      ? `有 ${selected.media} 張照片`
                      : "沒有附照片"}
                  </span>
                </div>
                <button>查看完整回報　↗</button>
              </div>
              <div className={styles.actions}>
                <span>
                  處理狀態：<strong>{statusLabel[selectedStatus]}</strong>
                </span>
                <div>
                  <button
                    className={
                      selectedStatus === "follow_up"
                        ? styles.actionSelected
                        : ""
                    }
                    onClick={() => setStatus("follow_up")}
                  >
                    標記需追蹤
                  </button>
                  <button
                    className={
                      selectedStatus === "acknowledged"
                        ? styles.actionPrimary
                        : styles.actionPrimary
                    }
                    onClick={() => setStatus("acknowledged")}
                  >
                    ✓　已確認
                  </button>
                </div>
              </div>
            </article>
          </div>
        </section>
      </div>
    </main>
  );
}
