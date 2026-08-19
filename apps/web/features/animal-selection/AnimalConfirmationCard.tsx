"use client";

import React from "react";
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
  canReport: boolean;
};

type Props = {
  animal: AnimalCandidate;
  onConfirm: () => void;
  onReselect: () => void;
};

export function AnimalConfirmationCard({
  animal,
  onConfirm,
  onReselect,
}: Props) {
  return (
    <Card
      className="animal-confirmation-card"
      aria-labelledby="animal-confirmation-card-title"
    >
      <CardHeader>
        <CardTitle id="animal-confirmation-card-title">
          請確認回報對象
        </CardTitle>
      </CardHeader>
      <CardContent className="animal-confirmation-content">
        <div className="animal-confirmation-layout">
          <div className="animal-confirmation-media">
            {animal.photoUrl ? (
              <img src={animal.photoUrl} alt={`${animal.name} 的照片`} />
            ) : (
              <p>目前沒有照片</p>
            )}
          </div>
          <div className="animal-confirmation-details">
            <p>名稱：{animal.name}</p>
            <p>收容編號：{animal.shelterNumber ?? "未維護"}</p>
            {animal.cage && <p>籠位：{animal.cage}</p>}
            {animal.area && <p>區域：{animal.area}</p>}
            {!animal.cage && !animal.area && <p>籠位／區域：未維護</p>}
            <p>{animal.canReport ? "目前可回報" : "目前不可回報"}</p>
          </div>
        </div>
        <div className="animal-confirmation-actions">
          <Button
            type="button"
            onClick={onConfirm}
            disabled={!animal.canReport}
          >
            確認是這隻
          </Button>
          <Button variant="secondary" type="button" onClick={onReselect}>
            重新選擇
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
