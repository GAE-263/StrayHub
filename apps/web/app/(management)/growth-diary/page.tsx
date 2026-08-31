"use client";

import { useEffect, useState } from "react";
import { authFetch } from "../../../lib/auth";
import { Badge } from "../../../components/ui/badge";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PermissionDeniedState,
} from "../../../components/management/StateViews";

type GrowthDiaryMood = "positive" | "neutral" | "concern";

type GrowthDiaryEntry = {
  id: string;
  inquiry_id: string;
  animal_id: string;
  animal_name: string | null;
  shelter_number: string | null;
  photo_url: string | null;
  note: string | null;
  ai_mood: GrowthDiaryMood | null;
  ai_reply: string | null;
  ai_staff_summary: string | null;
  created_at: string;
};

const MOOD_LABEL: Record<GrowthDiaryMood, string> = {
  positive: "適應良好",
  neutral: "例行回報",
  concern: "需留意",
};

export default function GrowthDiaryPage() {
  const [items, setItems] = useState<GrowthDiaryEntry[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [permissionDenied, setPermissionDenied] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setPermissionDenied(false);
    void authFetch("/v1/management/growth-diary-entries", {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 403) {
          setItems(null);
          setPermissionDenied(true);
          return;
        }
        if (!response.ok)
          throw new Error(`毛孩日記載入失敗（HTTP ${response.status}）`);
        const data = (await response.json()) as { items: GrowthDiaryEntry[] };
        if (!controller.signal.aborted) setItems(data.items);
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted)
          setError(
            requestError instanceof Error
              ? requestError.message
              : "毛孩日記載入失敗",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  return (
    <section aria-labelledby="growth-diary-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">POST-ADOPTION FOLLOW-UP</span>
          <h1 id="growth-diary-title">毛孩日記</h1>
          <p>
            領養人透過 LINE
            記錄的毛孩成長狀況，作為後續追蹤領養狀況的依據。目前僅供檢視。
          </p>
        </div>
      </div>
      <section className="ui-card ui-card-padded">
        {loading ? <LoadingState title="正在載入成長日記…" /> : null}
        {permissionDenied ? (
          <PermissionDeniedState description="請切換到已授權收容所，或聯絡收容所管理者。" />
        ) : null}
        {error ? (
          <ErrorState title="無法載入毛孩日記" description={error} />
        ) : null}
        {!loading && !error && items?.length === 0 ? (
          <EmptyState
            title="目前還沒有成長日記紀錄"
            description="領養人透過 LINE 選單的「毛孩日記」記錄後會出現在這裡。"
          />
        ) : null}
        {!loading && !error && items?.length ? (
          <ul className="growth-diary-list" aria-label="毛孩日記清單">
            {items.map((entry) => (
              <li className="list-card" key={entry.id}>
                {entry.photo_url ? (
                  <img
                    className="growth-diary-photo"
                    src={entry.photo_url}
                    alt={`${entry.animal_name ?? "毛孩"}的成長日記照片`}
                  />
                ) : null}
                <div>
                  <strong>
                    {entry.animal_name ?? "未知動物"}
                    {entry.shelter_number ? `／${entry.shelter_number}` : ""}
                  </strong>
                  {entry.ai_mood ? (
                    <Badge className={`ui-badge-${entry.ai_mood}`}>
                      {MOOD_LABEL[entry.ai_mood]}
                    </Badge>
                  ) : null}
                  <p className="muted">
                    {new Date(entry.created_at).toLocaleString("zh-TW")}
                  </p>
                  {entry.note ? <p>{entry.note}</p> : null}
                  {entry.ai_staff_summary ? (
                    <p className="muted">
                      🤖 AI 觀察摘要：{entry.ai_staff_summary}
                    </p>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </section>
  );
}
