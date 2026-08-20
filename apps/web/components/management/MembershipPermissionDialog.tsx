"use client";

import React from "react";
import { AlertDialog } from "../ui/alert-dialog";
import { Button } from "../ui/button";

export function MembershipPermissionDialog({
  open,
  title = "確認權限調整",
  shelterName,
  identity,
  operation,
  before,
  after,
  adminCountBefore,
  adminCountAfter,
  authorizationImpact,
  confirmLabel = "確認調整",
  closeLabel = "關閉權限確認",
  onClose,
  onConfirm,
  confirming = false,
  destructive = false,
}: {
  open: boolean;
  title?: string;
  shelterName?: string;
  identity: string;
  operation: string;
  before: string;
  after: string;
  adminCountBefore?: number | null;
  adminCountAfter?: number | null;
  authorizationImpact?: string;
  confirmLabel?: string;
  closeLabel?: string;
  onClose: () => void;
  onConfirm: () => void;
  confirming?: boolean;
  destructive?: boolean;
}) {
  return (
    <AlertDialog
      open={open}
      title={title}
      closeLabel={closeLabel}
      className="permission-confirmation-dialog"
      onClose={onClose}
    >
      <div className="permission-confirmation-content">
        {shelterName ? (
          <p>
            <strong>收容所：</strong>
            {shelterName}
          </p>
        ) : null}
        <p>
          <strong>目標：</strong>
          {identity}
        </p>
        <p>
          <strong>動作：</strong>
          {operation}
        </p>
        <dl className="permission-confirmation-diff">
          <div>
            <dt>目前</dt>
            <dd>{before}</dd>
          </div>
          <div>
            <dt>變更後</dt>
            <dd>{after}</dd>
          </div>
        </dl>
        {adminCountBefore != null && adminCountAfter != null ? (
          <p>
            <strong>啟用中收容所管理員：</strong>
            {adminCountBefore} → {adminCountAfter} 人
          </p>
        ) : null}
        {authorizationImpact ? <p>{authorizationImpact}</p> : null}
        <div className="dialog-actions">
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={confirming}
          >
            取消
          </Button>
          <Button
            type="button"
            variant={destructive ? "destructive" : "default"}
            onClick={onConfirm}
            disabled={confirming}
          >
            {confirming ? "處理中…" : confirmLabel}
          </Button>
        </div>
      </div>
    </AlertDialog>
  );
}
