import React from "react";

export function MedicalHistoryEntry({
  title,
  content,
}: {
  title: string;
  content: string;
}) {
  return (
    <article className="list-card">
      <div>
        <strong>{title}</strong>
        <p>{content}</p>
      </div>
    </article>
  );
}
