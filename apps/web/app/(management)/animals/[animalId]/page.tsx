"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Breadcrumbs } from "../../../../components/management/Breadcrumbs";
import { authFetch } from "../../../../lib/auth";
import {
  ErrorState,
  LoadingState,
} from "../../../../components/management/StateViews";

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

  if (error)
    return (
      <main>
        <ErrorState title="無法載入動物檔案" description={error} />
      </main>
    );
  if (!animal)
    return (
      <main>
        <LoadingState title="正在載入動物檔案…" />
      </main>
    );

  return (
    <main aria-labelledby="animal-profile-title">
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
        <Link className="button" href={`/animals/${animal.id}/timeline`}>
          開啟近期歷程
        </Link>
      </div>
      <div className="content-grid">
        <section className="panel" aria-labelledby="animal-summary-title">
          <h2 id="animal-summary-title">基本資料</h2>
          <dl className="detail-list">
            <div>
              <dt>收容編號</dt>
              <dd>{animal.shelter_number}</dd>
            </div>
            <div>
              <dt>目前狀態</dt>
              <dd>
                <span className="badge">{animal.status}</span>
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
        </section>
        <section className="panel" aria-labelledby="animal-actions-title">
          <h2 id="animal-actions-title">工作入口</h2>
          <Link className="link-card" href={`/animals/${animal.id}/timeline`}>
            <strong>Timeline</strong>
            <p className="muted">查看近 14 日、多筆回報與 AI 狀態。</p>
          </Link>
          <Link className="link-card" href="/settings/qr-codes">
            <strong>QR 綁定</strong>
            <p className="muted">前往管理此收容所的 QR 綁定。</p>
          </Link>
        </section>
      </div>
    </main>
  );
}
