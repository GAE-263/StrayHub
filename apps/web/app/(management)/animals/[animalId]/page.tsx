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
import { Toast } from "../../../../components/ui/toast";
import { AnimalCareQrCard } from "../../../../features/animal-management/AnimalCareQrCard";
import { AnimalBasicProfile } from "../../../../features/animal-management/AnimalBasicProfile";
import type { ManagementAnimal as Animal } from "../../../../lib/animal-profile";

type Props = { params: Promise<{ animalId: string }> };

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
  const [toast, setToast] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setAnimal(null);
    setError("");
    void authFetch(`/v1/management/animals/${animalId}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`動物檔案載入失敗（HTTP ${response.status}）`);
        const data = (await response.json()) as { animal: Animal };
        if (!controller.signal.aborted) setAnimal(data.animal);
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted)
          setError(
            requestError instanceof Error
              ? requestError.message
              : "動物檔案載入失敗",
          );
      });
    return () => controller.abort();
  }, [animalId]);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      authFetch(`/v1/management/care-agenda?animal_id=${animalId}`, {
        signal: controller.signal,
      }),
      authFetch(`/v1/animals/${animalId}/timeline`, {
        signal: controller.signal,
      }),
    ])
      .then(async ([agendaResponse, timelineResponse]) => {
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
        if (controller.signal.aborted) return;
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
      })
      .catch(() => {
        // This optional summary must not publish errors/results after unmount.
      });
    return () => controller.abort();
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
    <section
      className="animal-profile-page"
      aria-labelledby="animal-profile-title"
    >
      <Breadcrumbs
        items={[
          { label: "動物檔案", href: "/animals" },
          { label: animal.name },
        ]}
      />
      <div className="page-heading animal-profile-hero">
        <div className="animal-profile-identity">
          <div className="animal-profile-number" aria-label="收容編號">
            <span>收容編號</span>
            <strong>{animal.shelter_number}</strong>
          </div>
          <div className="animal-profile-title-block">
            <span className="eyebrow">ANIMAL PROFILE · 動物檔案</span>
            <div className="animal-profile-name-row">
              <h1 id="animal-profile-title">{animal.name}</h1>
              <Badge
                className="animal-profile-status"
                data-status={animal.status}
              >
                {statusLabel(animal.status)}
              </Badge>
            </div>
            <p>
              目前位置：{animal.area_path ?? animal.area_name ?? "尚未分配區域"}
            </p>
          </div>
        </div>
        <Link
          className="ui-button ui-button-default animal-profile-history-action"
          href={`/animals/${animal.id}/timeline`}
        >
          查看近期歷程
          <span aria-hidden="true">→</span>
        </Link>
      </div>
      <div className="content-grid animal-profile-grid">
        <div className="animal-profile-main-column">
          <AnimalBasicProfile
            key={`${animal.organization_id}:${animal.id}`}
            animal={animal}
            onSaved={setAnimal}
          />
          <AnimalTodaySummary
            hasActivity={todaySummary.hasActivity}
            pendingCount={todaySummary.pending}
            overdueCount={todaySummary.overdue}
            localToday={todaySummary.today}
            state={todaySummary.state}
          />
          <Card
            className="ui-card-padded animal-profile-workbench"
            aria-labelledby="animal-actions-title"
          >
            <div className="animal-profile-section-heading">
              <div>
                <span className="eyebrow">CARE WORKSPACE</span>
                <h2 id="animal-actions-title">照護工作台</h2>
              </div>
              <p>從今天最需要處理的事情開始。</p>
            </div>
            <nav
              className="animal-profile-action-list"
              aria-label="動物照護工作入口"
            >
              <Link
                className="animal-profile-action"
                href={`/animals/${animal.id}/timeline`}
              >
                <span>
                  <strong>近期歷程</strong>
                  <small>近 14 日回報、事件與 AI 狀態</small>
                </span>
                <span aria-hidden="true">→</span>
              </Link>
              <Link
                className="animal-profile-action"
                href={`/animals/${animal.id}/timeline?medical=1`}
              >
                <span>
                  <strong>醫療歷史</strong>
                  <small>就醫、用藥、疫苗與體重紀錄</small>
                </span>
                <span aria-hidden="true">→</span>
              </Link>
              <Link
                className="animal-profile-action"
                href={`/care-calendar?animal_id=${animal.id}`}
              >
                <span>
                  <strong>照護提醒</strong>
                  <small>今天與近期的待辦安排</small>
                </span>
                <span aria-hidden="true">→</span>
              </Link>
            </nav>
            <Button
              className="animal-profile-reminder-action"
              type="button"
              onClick={() => setReminderOpen(true)}
            >
              ＋ 建立照護提醒
            </Button>
          </Card>
        </div>
        <Card
          className="ui-card-padded animal-profile-record"
          aria-labelledby="animal-summary-title"
        >
          <div className="animal-profile-section-heading">
            <div>
              <span className="eyebrow">FILE STATUS</span>
              <h2 id="animal-summary-title">檔案狀態</h2>
            </div>
          </div>
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
              <dt>籠舍／區域</dt>
              <dd>{animal.area_path ?? animal.area_name ?? "未分配"}</dd>
            </div>
            <div>
              <dt>照片</dt>
              <dd>{animal.photo_key ? "已建檔" : "尚未建檔"}</dd>
            </div>
          </dl>
        </Card>
        <AnimalCareQrCard
          animal={{
            id: animal.id,
            organizationId: animal.organization_id,
            name: animal.name,
            shelterNumber: animal.shelter_number ?? "未提供",
            status: animal.status,
            areaName: animal.area_name,
          }}
        />
      </div>
      <ReminderFormDialog
        open={reminderOpen}
        animalId={animal.id}
        onClose={() => setReminderOpen(false)}
        onSaved={setToast}
      />
      {toast ? (
        <Toast messageKey={toast} onClose={() => setToast("")}>
          {toast}
        </Toast>
      ) : null}
    </section>
  );
}
