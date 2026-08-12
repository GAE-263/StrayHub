import React from "react";
import { Summary, summaryCards } from "./observationVocabulary";

type Props = { summary: Summary | null; loading?: boolean };

export function ObservationSummary({ summary, loading = false }: Props) {
  const cards = summary ? summaryCards(summary) : [];
  return (
    <section aria-labelledby="observation-summary-title">
      <h2 className="sr-only" id="observation-summary-title">
        觀察詞彙摘要
      </h2>
      <div className="observation-summary-grid">
        {cards.map(([label, value]) => (
          <article className="metric-card" key={label}>
            <span>{label}</span>
            <strong>{loading ? "—" : value}</strong>
          </article>
        ))}
        {!summary && loading ? (
          <article
            className="metric-card metric-card-loading"
            aria-hidden="true"
          >
            <span>正在載入摘要</span>
            <strong>—</strong>
          </article>
        ) : null}
      </div>
    </section>
  );
}
