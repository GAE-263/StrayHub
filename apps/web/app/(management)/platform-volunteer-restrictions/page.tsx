"use client";

import { useEffect, useState } from "react";

import { Alert } from "../../../components/ui/alert";
import { Button } from "../../../components/ui/button";
import { authFetch } from "../../../lib/auth";

type ReviewItem = {
  restriction: {
    id: string;
    reason_category: string;
    starts_at: string;
    ends_at: string | null;
  };
  incident: {
    incident_type: string;
    severity: string;
    factual_summary: string;
    occurred_at: string;
  };
  originating_organization_name: string;
};

export default function PlatformVolunteerRestrictionsPage() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    const response = await authFetch("/v1/platform/volunteer-restrictions");
    if (!response.ok) throw new Error("無法載入平台志工限制審查");
    setItems((await response.json()) as ReviewItem[]);
  }

  useEffect(() => {
    void load()
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "載入失敗"),
      )
      .finally(() => setLoading(false));
  }, []);

  async function decide(id: string, decision: "approve" | "reject") {
    setError("");
    const response = await authFetch(
      `/v1/platform/volunteer-restrictions/${id}/decision`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, reason: "平台管理員完成正式審查" }),
      },
    );
    if (!response.ok) {
      setError("平台限制審查失敗，請重新載入後確認狀態");
      return;
    }
    await load();
  }

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">PLATFORM GOVERNANCE</span>
          <h1>志工平台限制審查</h1>
          <p>只有經平台管理員人工確認的限制，才會影響其他收容所的核准。</p>
        </div>
      </div>
      {loading ? <p role="status">載入審查案件中…</p> : null}
      {error ? <Alert role="alert">{error}</Alert> : null}
      {!loading && items.length === 0 ? <p>目前沒有待審查案件。</p> : null}
      <div className="space-y-3">
        {items.map((item) => (
          <article className="ui-card ui-card-padded" key={item.restriction.id}>
            <h2>{item.incident.incident_type}</h2>
            <p>
              提出收容所：{item.originating_organization_name}・嚴重程度：
              {item.incident.severity}
            </p>
            <p>{item.incident.factual_summary}</p>
            <p>限制類別：{item.restriction.reason_category}</p>
            <div className="button-row">
              <Button
                type="button"
                onClick={() => void decide(item.restriction.id, "approve")}
              >
                核准平台限制
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => void decide(item.restriction.id, "reject")}
              >
                駁回
              </Button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
