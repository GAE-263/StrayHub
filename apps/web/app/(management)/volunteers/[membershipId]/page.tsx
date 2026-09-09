"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { Alert } from "../../../../components/ui/alert";
import { Button } from "../../../../components/ui/button";
import { Input } from "../../../../components/ui/input";
import { authFetch } from "../../../../lib/auth";

type Statistics = {
  current_shelter_visits: number;
  total_strayhub_visits: number;
  visits_last_180_days: number;
  visits_last_90_days: number;
  visits_last_30_days: number;
  last_visit_at: string | null;
  active_months_last_6_months: number;
  recent_status: string;
};

type VolunteerProfile = {
  membership_id: string;
  volunteer_no: string;
  label: string;
  membership_status: string;
  can_assist_new_volunteers: boolean;
  statistics: Statistics;
  notes: Array<{
    id: string;
    content: string;
    author_display_name: string;
    created_at: string;
  }>;
  incidents: Array<{
    id: string;
    incident_type: string;
    severity: string;
    factual_summary: string;
    occurred_at: string;
    status: string;
  }>;
  restrictions: Array<{
    id: string;
    scope: "SHELTER" | "PLATFORM";
    reason_category: string;
    status: string;
    starts_at: string;
    ends_at: string | null;
  }>;
};

const STATUS_LABELS: Record<string, string> = {
  new: "新加入",
  consistently_active: "持續參與",
  recently_active: "近期活躍",
  less_recently_active: "近期較少出現",
  active: "穩定參與",
};

export default function VolunteerProfilePage({
  params,
}: {
  params: Promise<{ membershipId: string }>;
}) {
  const { membershipId } = use(params);
  const [organizationId, setOrganizationId] = useState("");
  const [profile, setProfile] = useState<VolunteerProfile | null>(null);
  const [note, setNote] = useState("");
  const [incidentType, setIncidentType] = useState("");
  const [incidentSummary, setIncidentSummary] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function load(orgId: string) {
    const response = await authFetch(
      `/v1/organizations/${orgId}/volunteers/${membershipId}`,
    );
    if (!response.ok) throw new Error("無法載入志工資料");
    setProfile((await response.json()) as VolunteerProfile);
  }

  useEffect(() => {
    const orgId = window.sessionStorage.getItem("active_organization_id") ?? "";
    setOrganizationId(orgId);
    if (orgId) void load(orgId).catch((reason) => setError(reason.message));
  }, [membershipId]);

  async function addNote() {
    if (!note.trim()) return;
    setSaving(true);
    setError("");
    try {
      const response = await authFetch(
        `/v1/organizations/${organizationId}/volunteers/${membershipId}/notes`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: note.trim() }),
        },
      );
      if (!response.ok) throw new Error("新增備註失敗");
      setNote("");
      await load(organizationId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "新增備註失敗");
    } finally {
      setSaving(false);
    }
  }

  async function toggleAssist() {
    if (!profile) return;
    setSaving(true);
    try {
      const response = await authFetch(
        `/v1/organizations/${organizationId}/volunteers/${membershipId}/assist-flag`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            can_assist_new_volunteers: !profile.can_assist_new_volunteers,
          }),
        },
      );
      if (!response.ok) throw new Error("更新標記失敗");
      await load(organizationId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "更新標記失敗");
    } finally {
      setSaving(false);
    }
  }

  async function addIncident() {
    if (!incidentType.trim() || !incidentSummary.trim()) return;
    setSaving(true);
    try {
      const response = await authFetch(
        `/v1/organizations/${organizationId}/volunteers/${membershipId}/incidents`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            incident_type: incidentType.trim(),
            severity: "medium",
            factual_summary: incidentSummary.trim(),
            occurred_at: new Date().toISOString(),
          }),
        },
      );
      if (!response.ok) throw new Error("建立正式事件失敗");
      setIncidentType("");
      setIncidentSummary("");
      await load(organizationId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "建立正式事件失敗");
    } finally {
      setSaving(false);
    }
  }

  async function reviewIncident(
    incidentId: string,
    decision: "confirm" | "dismiss",
  ) {
    setSaving(true);
    try {
      const response = await authFetch(
        `/v1/organizations/${organizationId}/volunteer-incidents/${incidentId}/decision`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision }),
        },
      );
      if (!response.ok) throw new Error("事件審查失敗");
      await load(organizationId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "事件審查失敗");
    } finally {
      setSaving(false);
    }
  }

  async function requestRestriction(
    incidentId: string,
    scope: "SHELTER" | "PLATFORM",
  ) {
    setSaving(true);
    try {
      const response = await authFetch(
        `/v1/organizations/${organizationId}/volunteer-incidents/${incidentId}/restrictions`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            scope,
            reason_category: "service_safety",
            starts_at: new Date().toISOString(),
            ends_at: null,
          }),
        },
      );
      if (!response.ok) throw new Error("建立限制失敗");
      await load(organizationId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "建立限制失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">VOLUNTEER PROFILE</span>
          <h1>{profile?.label ?? "志工資料"}</h1>
          <p>服務統計由既有照護回報自動產生；備註與管理標記皆為選填。</p>
        </div>
        <Link href="/volunteers/access">返回志工授權</Link>
      </div>
      {error ? <Alert role="alert">{error}</Alert> : null}
      {!profile && !error ? <p role="status">正在載入志工資料…</p> : null}
      {profile ? (
        <div className="space-y-4">
          <section className="ui-card ui-card-padded">
            <h2>服務概況</h2>
            <dl className="summary-grid">
              <div>
                <dt>本收容所</dt>
                <dd>{profile.statistics.current_shelter_visits} 次</dd>
              </div>
              <div>
                <dt>StrayHub 累積</dt>
                <dd>{profile.statistics.total_strayhub_visits} 次</dd>
              </div>
              <div>
                <dt>最近半年</dt>
                <dd>{profile.statistics.visits_last_180_days} 次</dd>
              </div>
              <div>
                <dt>最近三個月</dt>
                <dd>{profile.statistics.visits_last_90_days} 次</dd>
              </div>
              <div>
                <dt>最近服務</dt>
                <dd>
                  {profile.statistics.last_visit_at
                    ? new Date(
                        profile.statistics.last_visit_at,
                      ).toLocaleDateString("zh-TW")
                    : "尚無紀錄"}
                </dd>
              </div>
              <div>
                <dt>近期狀態</dt>
                <dd>
                  ● {STATUS_LABELS[profile.statistics.recent_status] ?? "—"}
                </dd>
              </div>
            </dl>
            <Button type="button" onClick={toggleAssist} disabled={saving}>
              {profile.can_assist_new_volunteers
                ? "取消「可協助新人」"
                : "⭐ 標記為可協助新人"}
            </Button>
          </section>

          <section className="ui-card ui-card-padded">
            <h2>本所備註</h2>
            {profile.notes.length ? (
              <ul className="space-y-2">
                {profile.notes.map((item) => (
                  <li key={item.id}>
                    <small>
                      {new Date(item.created_at).toLocaleDateString("zh-TW")}・
                      {item.author_display_name}
                    </small>
                    <p>{item.content}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p>目前沒有備註；不需為每次服務填寫。</p>
            )}
            <label htmlFor="volunteer-note">新增備註（選填）</label>
            <textarea
              id="volunteer-note"
              maxLength={2000}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
            <Button
              type="button"
              onClick={addNote}
              disabled={saving || !note.trim()}
            >
              新增備註
            </Button>
          </section>

          <section className="ui-card ui-card-padded">
            <h2>正式事件</h2>
            <p className="muted">一般備註不會自動成為事件或平台限制。</p>
            {profile.incidents.map((incident) => (
              <article key={incident.id} className="rounded border p-3">
                <strong>{incident.incident_type}</strong>・{incident.severity}
                <p>{incident.factual_summary}</p>
                <p>狀態：{incident.status}</p>
                {incident.status === "reported" ? (
                  <div className="button-row">
                    <Button
                      type="button"
                      onClick={() => reviewIncident(incident.id, "confirm")}
                      disabled={saving}
                    >
                      確認事件
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => reviewIncident(incident.id, "dismiss")}
                      disabled={saving}
                    >
                      駁回事件
                    </Button>
                  </div>
                ) : null}
                {incident.status === "confirmed" ? (
                  <div className="button-row">
                    <Button
                      type="button"
                      onClick={() => requestRestriction(incident.id, "SHELTER")}
                      disabled={saving}
                    >
                      建立本所限制
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() =>
                        requestRestriction(incident.id, "PLATFORM")
                      }
                      disabled={saving}
                    >
                      送平台限制審查
                    </Button>
                  </div>
                ) : null}
              </article>
            ))}
            {profile.restrictions.length ? (
              <div>
                <h3>限制紀錄</h3>
                <ul>
                  {profile.restrictions.map((restriction) => (
                    <li key={restriction.id}>
                      {restriction.scope}・{restriction.reason_category}・
                      {restriction.status}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            <label htmlFor="incident-type">事件類型</label>
            <Input
              id="incident-type"
              value={incidentType}
              onChange={(event) => setIncidentType(event.target.value)}
            />
            <label htmlFor="incident-summary">客觀事件摘要</label>
            <textarea
              id="incident-summary"
              maxLength={2000}
              value={incidentSummary}
              onChange={(event) => setIncidentSummary(event.target.value)}
            />
            <Button
              type="button"
              onClick={addIncident}
              disabled={
                saving || !incidentType.trim() || !incidentSummary.trim()
              }
            >
              建立正式事件
            </Button>
          </section>
        </div>
      ) : null}
    </div>
  );
}
