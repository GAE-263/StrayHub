import React from "react";

export function MedicalHistoryAuditPanel({
  items = [],
}: {
  items?: Array<{ action: string; created_at: string }>;
}) {
  return (
    <details>
      <summary>修改紀錄</summary>
      {items.length ? (
        items.map((item) => (
          <p key={`${item.action}-${item.created_at}`}>
            {item.action} · {item.created_at}
          </p>
        ))
      ) : (
        <p>目前沒有可顯示的修改紀錄。</p>
      )}
    </details>
  );
}
