import React from "react";
import { AlertTriangle, Inbox, ShieldAlert } from "lucide-react";
import { getStatusSemantics, type UIStatusKind } from "./ui-status";

type StateProps = {
  title: string;
  description?: string;
  action?: React.ReactNode;
  kind?: UIStatusKind;
};

function StateView({
  title,
  description,
  action,
  kind,
  role,
}: StateProps & { role?: "status" | "alert" }) {
  const semantics = kind ? getStatusSemantics(kind) : null;
  const animated = kind === "loading" || kind === "saving";
  const StaticIcon =
    kind === "empty"
      ? Inbox
      : kind === "error"
        ? AlertTriangle
        : kind === "permission-denied"
          ? ShieldAlert
          : null;

  return (
    <div
      className={`state-card ${kind ? `state-${semantics?.tone}` : ""}`}
      role={role}
      aria-live={semantics?.ariaLive ?? "polite"}
    >
      {animated ? (
        <span className="loading-dot" aria-hidden="true" />
      ) : StaticIcon && kind ? (
        <StaticIcon
          className="state-icon"
          data-state-icon={kind}
          size={20}
          aria-hidden="true"
        />
      ) : null}
      <div>
        <strong>{title}</strong>
        {description ? <p>{description}</p> : null}
        {action ? <div className="state-action">{action}</div> : null}
      </div>
    </div>
  );
}

export function LoadingState({ title, description }: StateProps) {
  return (
    <StateView
      title={title}
      description={description}
      kind="loading"
      role="status"
    />
  );
}

export function SavingState({
  title = "儲存中…",
  description,
  action,
}: Partial<StateProps> = {}) {
  return (
    <StateView
      title={title}
      description={description}
      action={action}
      kind="saving"
      role="status"
    />
  );
}

export function EmptyState({ title, description, action }: StateProps) {
  return (
    <StateView
      title={title}
      description={description}
      action={action}
      kind="empty"
      role="status"
    />
  );
}

export function ErrorState({ title, description, action }: StateProps) {
  return (
    <StateView
      title={title}
      description={description}
      action={action}
      kind="error"
      role="alert"
    />
  );
}

export function PermissionDeniedState({
  title = "沒有查看權限",
  description,
  action,
}: Partial<StateProps> = {}) {
  return (
    <StateView
      title={title}
      description={description}
      action={action}
      kind="permission-denied"
      role="status"
    />
  );
}
