"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Breadcrumbs } from "../../../../components/management/Breadcrumbs";
import { authFetch } from "../../../../lib/auth";
import {
  ErrorState,
  LoadingState,
} from "../../../../components/management/StateViews";
import { statusLabel } from "../../../../components/management/ui-status";
import { Badge } from "../../../../components/ui/badge";
import { Card } from "../../../../components/ui/card";
import { Button } from "../../../../components/ui/button";
import { ReminderFormDialog } from "../../../../features/medical-care/ReminderFormDialog";
import { AnimalTodaySummary } from "../../../../features/medical-care/AnimalTodaySummary";

type Props = { params: Promise<{ animalId: string }> };
type Animal = {
  id: string;
  name: string;
  shelter_number: string;
  status: string;
  photo_key: string | null;
  area_name: string | null;
  area_type: string | null;
};

export default function AnimalProfilePage({ params }: Props) {
  const { animalId } = use(params);
  const [animal, setAnimal] = useState<Animal | null>(null);
  const [error, setError] = useState("");
  const [todaySummary, setTodaySummary] = useState({
    hasActivity: false,
    pending: 0,
    overdue: 0,
    today: "",
    state: undefined as
      "no_activity" | "events_no_todos" | "pending" | "overdue" | undefined,
  });
  const [reminderOpen, setReminderOpen] = useState(false);

  useEffect(() => {
    void authFetch(`/v1/management/animals/${animalId}`)
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`動物檔案載入失敗（HTTP ${response.status}）`);
        const data = (await response.json()) as { animal: Animal };
        setAnimal(data.animal);
      })
      .catch((requestError: unknown) =>
        setError(
          requestError instanceof Error
            ? requestError.message
            : "動物檔案載入失敗",
        ),
      );
  }, [animalId]);

  useEffect(() => {
    void Promise.all([
      authFetch(`/v1/management/care-agenda?animal_id=${animalId}`),
      authFetch(`/v1/animals/${animalId}/timeline`),
    ]).then(async ([agendaResponse, timelineResponse]) => {
      const data = agendaResponse.ok
        ? ((await agendaResponse.json()) as {
            local_today?: string;
            totals?: {
              today_pending?: number;
              overdue?: number;
              today_resolved?: number;
            };
            today_state?:
              "no_activity" | "events_no_todos" | "pending" | "overdue";
          })
        : null;
      if (!data) return;
      const timeline = timelineResponse.ok
        ? ((await timelineResponse.json()) as {
            days?: Array<{
              date: string;
              has_activity?: boolean;
              events?: unknown[];
              scheduled?: unknown[];
            }>;
          })
        : null;
      const todayTimeline = timeline?.days?.find(
        (day) => day.date === data.local_today,
      );
      const timelineHasActivity = Boolean(
        todayTimeline?.has_activity ||
        todayTimeline?.events?.length ||
        todayTimeline?.scheduled?.length,
      );
      setTodaySummary({
        hasActivity:
          Boolean(
            (data.totals?.today_resolved ?? 0) +
            (data.totals?.today_pending ?? 0),
          ) || timelineHasActivity,
        pending: data.totals?.today_pending ?? 0,
        overdue: data.totals?.overdue ?? 0,
        today: data.local_today ?? "",
        state: data.today_state,
      });
    });
  }, [animalId]);

  if (error)
    return (
      <div>
        <ErrorState title="無法載入動物檔案" description={error} />
      </div>
    );
  if (!animal)
    return (
      <div>
        <LoadingState title="正在載入動物檔案…" />
      </div>
    );

  return (
    <section aria-labelledby="animal-profile-title">
      <Breadcrumbs
        items={[
          { label: "動物檔案", href: "/animals" },
          { label: animal.name },
        ]}
      />
      <div className="page-heading">
        <div>
          <span className="eyebrow">ANIMAL PROFILE</span>
          <h1 id="animal-profile-title">{animal.name}</h1>
          <p>
            {animal.shelter_number} · {animal.area_name ?? "未分配區域"}
          </p>
        </div>
        <Link
          className="ui-button ui-button-default"
          href={`/animals/${animal.id}/timeline`}
        >
          開啟近期歷程
        </Link>
      </div>
      <div className="content-grid">
        <AnimalTodaySummary
          hasActivity={todaySummary.hasActivity}
          pendingCount={todaySummary.pending}
          overdueCount={todaySummary.overdue}
          localToday={todaySummary.today}
          state={todaySummary.state}
        />
        <Card className="ui-card-padded" aria-labelledby="animal-summary-title">
          <h2 id="animal-summary-title">基本資料</h2>
          <dl className="detail-list">
            <div>
              <dt>收容編號</dt>
              <dd>{animal.shelter_number}</dd>
            </div>
            <div>
              <dt>目前狀態</dt>
              <dd>
                <Badge>{statusLabel(animal.status)}</Badge>
              </dd>
            </div>
            <div>
              <dt>Cage／Area</dt>
              <dd>
                {animal.area_name ?? "未分配"}{" "}
                {animal.area_type ? `（${animal.area_type}）` : ""}
              </dd>
            </div>
            <div>
              <dt>照片</dt>
              <dd>{animal.photo_key ? "已設定" : "尚未設定"}</dd>
            </div>
          </dl>
        </Card>
        <Card className="ui-card-padded" aria-labelledby="animal-actions-title">
          <h2 id="animal-actions-title">工作入口</h2>
          <Link className="link-card" href={`/animals/${animal.id}/timeline`}>
            <strong>Timeline</strong>
            <p className="muted">查看近 14 日、多筆回報與 AI 狀態。</p>
          </Link>
          <Link
            className="link-card"
            href={`/animals/${animal.id}/timeline?medical=1`}
          >
            <strong>醫療歷史</strong>
            <p className="muted">查看就醫、用藥、疫苗與體重紀錄。</p>
          </Link>
          <Link
            className="link-card"
            href={`/care-calendar?animal_id=${animal.id}`}
          >
            <strong>照護提醒</strong>
            <p className="muted">查看這隻動物今天與近期的待辦。</p>
          </Link>
          <Button type="button" onClick={() => setReminderOpen(true)}>
            建立提醒
          </Button>
          <Link className="link-card" href="/settings/qr-codes">
            <strong>QR 綁定</strong>
            <p className="muted">前往管理此收容所的 QR 綁定。</p>
          </Link>
        </Card>
      </div>
      <ReminderFormDialog
        open={reminderOpen}
        animalId={animal.id}
        onClose={() => setReminderOpen(false)}
      />
    </section>
  );
}
