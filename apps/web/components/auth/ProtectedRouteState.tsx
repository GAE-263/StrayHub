"use client";

import React from "react";
import type { RouteDecisionState } from "../../lib/route-access";
import { Button } from "../ui/button";
import { LoadingState } from "../management/StateViews";

export type ProtectedRouteStateKind = RouteDecisionState | "access-unavailable";

type ProtectedRouteStateProps = {
  state: ProtectedRouteStateKind;
  children?: React.ReactNode;
  onRetry?: () => void;
  onReenter?: () => void;
  onBack?: () => void;
  onContactManager?: () => void;
  onReapply?: () => void;
  onWaitApproval?: () => void;
};

function InteractiveState({
  title,
  description,
  role,
  actions,
}: {
  title: string;
  description: string;
  role: "status" | "alert";
  actions: React.ReactNode;
}) {
  return (
    <div className="state-card state-danger">
      <div role={role} aria-live={role === "alert" ? "assertive" : "polite"}>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
      {actions ? <div className="state-action">{actions}</div> : null}
    </div>
  );
}

export function ProtectedRouteState({
  state,
  children,
  onRetry,
  onReenter,
  onBack,
  onContactManager,
  onReapply,
  onWaitApproval,
}: ProtectedRouteStateProps) {
  if (state === "allowed") return <>{children}</>;

  if (state === "checking") {
    return (
      <LoadingState
        title="正在確認登入狀態"
        description="請稍候，受保護內容會在確認完成後顯示。"
      />
    );
  }

  if (state === "redirecting") {
    return (
      <LoadingState
        title="正在前往安全入口"
        description="請稍候，尚未顯示受保護內容。"
      />
    );
  }

  if (state === "context-required") {
    return (
      <InteractiveState
        title="需要確認目前收容所"
        description="目前尚未確認可操作的收容所，請重試或返回。"
        role="status"
        actions={
          <>
            {onRetry ? <Button onClick={onRetry}>重試</Button> : null}
            {onBack ? (
              <Button variant="secondary" onClick={onBack}>
                返回
              </Button>
            ) : null}
            {onContactManager ? (
              <Button variant="ghost" onClick={onContactManager}>
                聯絡管理者
              </Button>
            ) : null}
          </>
        }
      />
    );
  }

  if (state === "temporary-error") {
    return (
      <InteractiveState
        title="服務暫時無法使用"
        description="目前無法完成登入狀態確認，請重試或返回。"
        role="alert"
        actions={
          <>
            {onRetry ? <Button onClick={onRetry}>重試</Button> : null}
            {onBack ? (
              <Button variant="secondary" onClick={onBack}>
                返回
              </Button>
            ) : null}
          </>
        }
      />
    );
  }

  if (state === "re-entry") {
    return (
      <InteractiveState
        title="重新進入志工入口"
        description="目前登入狀態已結束，請重新進入志工入口或回上一頁。"
        role="alert"
        actions={
          <>
            {onReenter ? <Button onClick={onReenter}>重新進入</Button> : null}
            {onBack ? (
              <Button variant="secondary" onClick={onBack}>
                返回
              </Button>
            ) : null}
          </>
        }
      />
    );
  }

  return (
    <InteractiveState
      title="目前沒有可用的志工權限"
      description="請等待核准、重新報名或聯絡管理者。"
      role="alert"
      actions={
        <>
          {onWaitApproval ? (
            <Button onClick={onWaitApproval}>等待核准</Button>
          ) : null}
          {onReapply ? (
            <Button variant="secondary" onClick={onReapply}>
              重新報名
            </Button>
          ) : null}
          {onContactManager ? (
            <Button variant="ghost" onClick={onContactManager}>
              聯絡管理者
            </Button>
          ) : null}
          {onBack ? (
            <Button variant="ghost" onClick={onBack}>
              返回
            </Button>
          ) : null}
        </>
      }
    />
  );
}
