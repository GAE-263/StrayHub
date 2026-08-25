"use client";

import React, { useEffect, useRef, useState } from "react";
import { Button } from "../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";

type AnimalCandidate = {
  id: string;
  name: string;
  shelterNumber?: string | null;
  photoUrl?: string | null;
  cage?: string | null;
  area?: string | null;
  shelterName: string;
  canReport: boolean;
};

type Props = {
  animal: AnimalCandidate;
  busy?: boolean;
  onConfirm: () => void;
  onReselect: () => void;
};

export function AnimalConfirmationCard({
  animal,
  busy = false,
  onConfirm,
  onReselect,
}: Props) {
  const containerRef = useRef<HTMLElement>(null);
  const [photoFailed, setPhotoFailed] = useState(false);

  useEffect(() => {
    setPhotoFailed(false);
    containerRef.current?.focus();
  }, [animal.id]);

  return (
    <section
      ref={containerRef}
      className="animal-confirmation-card"
      aria-labelledby="animal-confirmation-card-title"
      tabIndex={-1}
    >
      <Card>
        <CardHeader>
          <CardTitle id="animal-confirmation-card-title">
            確認照護動物
          </CardTitle>
        </CardHeader>
        <CardContent className="animal-confirmation-content">
          <div className="animal-confirmation-layout">
            <div className="animal-confirmation-media">
              {animal.photoUrl && !photoFailed ? (
                <img
                  src={animal.photoUrl}
                  alt={`${animal.name} 的照片`}
                  onError={() => setPhotoFailed(true)}
                />
              ) : (
                <p>目前沒有照片</p>
              )}
            </div>
            <div className="animal-confirmation-details">
              <strong>{animal.name}</strong>
              <p>收容編號：{animal.shelterNumber ?? "未維護"}</p>
              {animal.cage && <p>犬舍／籠位：{animal.cage}</p>}
              {animal.area && <p>區域：{animal.area}</p>}
              {!animal.cage && !animal.area && <p>犬舍／區域：未維護</p>}
              <p>收容所：{animal.shelterName}</p>
            </div>
          </div>
          <div className="animal-confirmation-actions">
            <Button
              type="button"
              onClick={onConfirm}
              disabled={!animal.canReport || busy}
            >
              {busy ? "處理中…" : "確認並開始回報"}
            </Button>
            <Button
              variant="secondary"
              type="button"
              onClick={onReselect}
              disabled={busy}
            >
              重新掃描
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
