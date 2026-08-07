"use client";

import { AnimalConfirmationCard } from "../../../features/animal-selection/AnimalConfirmationCard";

export default function AnimalConfirmationPage() {
  return (
    <main>
      <h1>確認照護動物</h1>
      <AnimalConfirmationCard
        animal={{ id: "", name: "待選擇", canReport: false }}
        onConfirm={() => undefined}
        onReselect={() => undefined}
      />
    </main>
  );
}
