type StateProps = { title: string; description?: string };

export function LoadingState({ title, description }: StateProps) {
  return (
    <div className="state-card" role="status" aria-live="polite">
      <span className="loading-dot" aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        {description ? <p>{description}</p> : null}
      </div>
    </div>
  );
}

export function EmptyState({ title, description }: StateProps) {
  return (
    <div className="state-card empty-state">
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
    </div>
  );
}

export function ErrorState({ title, description }: StateProps) {
  return (
    <div className="state-card error-state" role="alert">
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
    </div>
  );
}
