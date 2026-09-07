"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, Sparkles } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { fetchGrowthDiaryDetail, updateGrowthDiaryStatus } from "./api";
import { DiaryPhoto } from "./DiaryPhoto";
import type { GrowthDiaryDetail, GrowthDiaryListItem } from "./types";
import styles from "./growth-diary.module.css";

const STATUS_COPY: Record<string, string> = {
  pending: "等待分析",
  processing: "分析中",
  succeeded: "分析完成",
  failed: "尚無分析",
  unconfigured: "尚無分析",
  not_applicable: "這篇日記沒有可分析的文字",
  legacy: "來源資訊未留存",
  unavailable: "尚無分析",
};

function formatSubmittedAt(value: string): string {
  return new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export function GrowthDiaryEntryCard({
  entry,
}: {
  entry: GrowthDiaryListItem;
}) {
  const concern = entry.ai_analysis.mood === "concern";
  const [detail, setDetail] = useState<GrowthDiaryDetail | null>(null);
  const [detailState, setDetailState] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [expanded, setExpanded] = useState(false);
  const [status, setStatus] = useState(entry.status ?? "new");
  const [statusState, setStatusState] = useState<"idle" | "loading" | "error">(
    "idle",
  );
  const request = useRef<AbortController | null>(null);
  const detailId = `growth-diary-provenance-${entry.id}`;

  useEffect(() => () => request.current?.abort(), []);

  async function toggleProvenance() {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (detail) return;

    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setDetailState("loading");
    try {
      const response = await fetchGrowthDiaryDetail(
        entry.id,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setDetail(response);
      setDetailState("ready");
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (!controller.signal.aborted) setDetailState("error");
    }
  }

  async function toggleStatus() {
    const nextStatus = status === "new" ? "reviewed" : "new";
    setStatusState("loading");
    try {
      const updated = await updateGrowthDiaryStatus(entry.id, nextStatus);
      setStatus(updated.status ?? nextStatus);
      setStatusState("idle");
    } catch {
      setStatusState("error");
    }
  }

  return (
    <article className={styles.timelineItem}>
      <span className={styles.timelineNode} aria-hidden="true" />
      <Card className={styles.entryCard}>
        <header className={styles.entryHeader}>
          <div className={styles.animalIdentity}>
            <span className={styles.animalMark} aria-hidden="true">
              🐾
            </span>
            <div>
              <h2>{entry.animal_name ?? "未命名毛孩"}</h2>
              <p>收容編號 {entry.shelter_number ?? "未提供"}</p>
            </div>
          </div>
          <time dateTime={entry.created_at}>
            {formatSubmittedAt(entry.created_at)}
          </time>
        </header>

        <div className={styles.reviewRow}>
          <Badge
            className={
              status === "new" ? styles.newBadge : styles.reviewedBadge
            }
          >
            {status === "new" ? "待查看" : "已查看"}
          </Badge>
          <Button
            type="button"
            variant="secondary"
            disabled={statusState === "loading"}
            onClick={() => void toggleStatus()}
          >
            {statusState === "loading" ? (
              "更新中…"
            ) : status === "new" ? (
              <>
                <Check size={15} aria-hidden="true" />
                標記已查看
              </>
            ) : (
              "標記待查看"
            )}
          </Button>
          {statusState === "error" ? (
            <span className={styles.statusError} role="alert">
              狀態未更新，請重試。
            </span>
          ) : null}
        </div>

        <div className={styles.originalSection}>
          <p className={styles.sectionLabel}>領養人原文</p>
          {entry.note ? (
            <p className={styles.note}>{entry.note}</p>
          ) : (
            <p className={styles.muted}>這篇日記沒有文字內容。</p>
          )}
          {entry.has_photo ? (
            <div className={styles.photoGrid}>
              {(entry.photo_endpoints?.length
                ? entry.photo_endpoints
                : [entry.photo_endpoint]
              ).map((_, index) => (
                <DiaryPhoto
                  key={`${entry.id}-${index}`}
                  entryId={entry.id}
                  photoIndex={entry.photo_endpoints?.length ? index : undefined}
                  alt={`${entry.animal_name ?? "未命名毛孩"}的日記照片 ${index + 1}`}
                />
              ))}
            </div>
          ) : null}
        </div>

        <section className={styles.aiSection} aria-label="AI 追蹤摘要">
          <div className={styles.aiHeading}>
            <div>
              <Sparkles size={16} aria-hidden="true" />
              <h3>AI 追蹤摘要</h3>
            </div>
            {concern ? (
              <Badge className={styles.concernBadge}>
                <AlertTriangle size={14} aria-hidden="true" />
                AI 建議人工查看
              </Badge>
            ) : null}
          </div>
          <p className={styles.aiDisclaimer}>
            AI 產生、未經人工確認，並非醫療診斷。
          </p>
          {entry.ai_analysis.staff_summary ? (
            <p className={styles.aiSummary}>
              {entry.ai_analysis.staff_summary}
            </p>
          ) : (
            <p className={styles.muted}>
              {STATUS_COPY[entry.ai_analysis.status] ?? "尚無分析"}
            </p>
          )}
          <Button
            type="button"
            variant="ghost"
            className={styles.provenanceButton}
            aria-expanded={expanded}
            aria-controls={detailId}
            onClick={() => void toggleProvenance()}
          >
            {expanded ? "隱藏 AI 來源" : "查看 AI 來源"}
          </Button>
          {expanded ? (
            <div id={detailId} className={styles.provenancePanel}>
              {detailState === "loading" ? (
                <p role="status">正在載入 AI 來源…</p>
              ) : detailState === "error" ? (
                <p role="alert">AI 來源資訊暫時無法載入，請收合後再試一次。</p>
              ) : detail?.ai_provenance.provenance_status ===
                "legacy_missing" ? (
                <p>來源資訊未留存</p>
              ) : detail ? (
                <>
                  <dl className={styles.provenanceGrid}>
                    <div>
                      <dt>模型</dt>
                      <dd>{detail.ai_provenance.model_name ?? "未提供"}</dd>
                    </div>
                    <div>
                      <dt>模型版本</dt>
                      <dd>{detail.ai_provenance.model_version ?? "未提供"}</dd>
                    </div>
                    <div>
                      <dt>Prompt 版本</dt>
                      <dd>{detail.ai_provenance.prompt_version ?? "未提供"}</dd>
                    </div>
                    <div>
                      <dt>Schema 版本</dt>
                      <dd>
                        {detail.ai_provenance.output_schema_version ?? "未提供"}
                      </dd>
                    </div>
                    <div>
                      <dt>分析時間</dt>
                      <dd>
                        {detail.ai_provenance.analyzed_at
                          ? formatSubmittedAt(detail.ai_provenance.analyzed_at)
                          : "未提供"}
                      </dd>
                    </div>
                  </dl>
                  <div>
                    <p className={styles.sectionLabel}>AI 原始輸出</p>
                    <pre className={styles.rawOutput}>
                      {typeof detail.ai_raw_output === "string"
                        ? detail.ai_raw_output
                        : JSON.stringify(detail.ai_raw_output, null, 2)}
                    </pre>
                  </div>
                </>
              ) : null}
            </div>
          ) : null}
        </section>
      </Card>
    </article>
  );
}
