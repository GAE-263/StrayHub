"use client";

import { use } from "react";
import { AssignedCareTask } from "../../../../features/medical-care/AssignedCareTask";

type Props = { params: Promise<{ occurrenceId: string }> };

export default function AssignedCarePage({ params }: Props) {
  const { occurrenceId } = use(params);

  return (
    <main className="volunteer-page" aria-labelledby="assigned-care-title">
      <h1 id="assigned-care-title">我的照護指派</h1>
      <p>此頁只顯示完成本次任務所需的資訊。</p>
      <AssignedCareTask occurrenceId={occurrenceId} />
    </main>
  );
}
