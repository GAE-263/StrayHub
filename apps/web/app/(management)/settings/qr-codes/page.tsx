"use client";

import Link from "next/link";
import React, { useEffect, useState } from "react";
import { authFetch, type CurrentUser } from "../../../../lib/auth";
import { canManageCareQr } from "../../../../lib/management-capabilities";
import { LoadingState } from "../../../../components/management/StateViews";
import { Alert } from "../../../../components/ui/alert";
import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../../components/ui/card";
import { Dialog } from "../../../../components/ui/dialog";
import { Toast } from "../../../../components/ui/toast";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../../../components/ui/table";

type Qr = {
  id: string;
  animal_id: string;
  status: string;
  revoked: boolean;
  deep_link: string | null;
};

type PendingQrAction = {
  id: string;
  animalId: string;
  action: "revoke" | "regenerate";
};

export default function QrCodesPage() {
  const [items, setItems] = useState<Qr[]>([]);
  const [canManage, setCanManage] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [pendingAction, setPendingAction] = useState<PendingQrAction | null>(
    null,
  );
  const load = () => {
    setLoading(true);
    void Promise.all([
      authFetch("/v1/management/qr-codes"),
      authFetch("/v1/auth/active-shelter-context"),
      authFetch("/v1/auth/me"),
    ])
      .then(async ([qrResponse, contextResponse, profileResponse]) => {
        if (!qrResponse.ok)
          throw new Error(`QR 清單載入失敗（HTTP ${qrResponse.status}）`);
        if (!contextResponse.ok || !profileResponse.ok)
          throw new Error("QR 管理權限載入失敗");
        const context = (await contextResponse.json()) as {
          organization_id: string;
        };
        const profile = (await profileResponse.json()) as CurrentUser;
        setItems(((await qrResponse.json()) as { items: Qr[] }).items);
        setCanManage(canManageCareQr(profile, context.organization_id));
      })
      .catch((requestError: unknown) =>
        setError(
          requestError instanceof Error
            ? requestError.message
            : "QR 清單載入失敗",
        ),
      )
      .finally(() => setLoading(false));
  };
  useEffect(load, []);
  const revoke = async (id: string) => {
    setError("");
    const response = await authFetch(`/v1/management/qr-codes/${id}/revoke`, {
      method: "POST",
    });
    if (!response.ok) setError(`QR 撤銷失敗（HTTP ${response.status}）`);
    else {
      setMessage("QR 已撤銷，已張貼的舊標籤無法再使用。");
      load();
    }
  };
  const regenerate = async (id: string) => {
    setError("");
    const response = await authFetch(
      `/v1/management/qr-codes/${id}/regenerate`,
      { method: "POST" },
    );
    if (!response.ok) {
      setError(`QR 重新產生失敗（HTTP ${response.status}）`);
      return;
    }
    setMessage("QR 已重新產生，請至動物檔案列印並更換舊標籤。");
    load();
  };

  const confirmPendingAction = async () => {
    const action = pendingAction;
    if (!action) return;
    setPendingAction(null);
    if (action.action === "revoke") await revoke(action.id);
    else await regenerate(action.id);
  };
  return (
    <section aria-labelledby="qr-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">CARE QR MANAGEMENT</span>
          <h1 id="qr-title">照護 QR 管理</h1>
          <p>QR 只提供動物候選查詢，不是授權憑證；請至動物檔案預覽與列印。</p>
        </div>
      </div>
      {error ? <Alert role="alert">{error}</Alert> : null}
      {message ? <Toast>{message}</Toast> : null}
      <Card>
        <CardHeader>
          <CardTitle>QR 紀錄</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <LoadingState title="正在載入 QR…" />
          ) : items.length === 0 ? (
            <p className="muted">
              目前沒有照護 QR 紀錄。請前往動物檔案建立照護 QR。
            </p>
          ) : (
            <Table>
              <TableHeader>
                <tr>
                  <TableHead>動物</TableHead>
                  <TableHead>狀態</TableHead>
                  <TableHead>操作</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{item.animal_id.slice(0, 8)}…</TableCell>
                    <TableCell>
                      <Badge>{item.status}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="p1-actions">
                        {item.status === "active" && !item.revoked ? (
                          <>
                            {item.deep_link ? (
                              <Link
                                className="ui-button ui-button-secondary"
                                href={`/animals/${item.animal_id}`}
                              >
                                前往重新列印
                              </Link>
                            ) : (
                              <span className="muted">
                                舊版 QR 無法重新列印
                              </span>
                            )}
                            {canManage ? (
                              <>
                                <Button
                                  variant="secondary"
                                  type="button"
                                  onClick={() =>
                                    setPendingAction({
                                      id: item.id,
                                      animalId: item.animal_id,
                                      action: "regenerate",
                                    })
                                  }
                                >
                                  重新產生新 QR
                                </Button>
                                <Button
                                  variant="destructive"
                                  type="button"
                                  onClick={() =>
                                    setPendingAction({
                                      id: item.id,
                                      animalId: item.animal_id,
                                      action: "revoke",
                                    })
                                  }
                                >
                                  撤銷 QR
                                </Button>
                              </>
                            ) : null}
                          </>
                        ) : (
                          <Link
                            className="ui-button ui-button-secondary"
                            href={`/animals/${item.animal_id}`}
                          >
                            前往動物檔案
                          </Link>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      {canManage ? (
        <Dialog
          open={pendingAction !== null}
          role="alertdialog"
          title={
            pendingAction?.action === "revoke"
              ? "確認撤銷 QR"
              : "重新產生新的照護 QR？"
          }
          onClose={() => setPendingAction(null)}
        >
          <p className="dialog-description">
            動物：{pendingAction?.animalId ?? "未知動物"}。
            {pendingAction?.action === "revoke"
              ? "撤銷後，目前的 QR 會立即失效，且不會建立新的 QR。請移除現場舊標籤。"
              : "重新產生後，目前的 QR 會立即失效。請列印新的 QR，並更換現場舊標籤。"}
          </p>
          <div className="dialog-actions">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setPendingAction(null)}
            >
              取消
            </Button>
            <Button
              type="button"
              variant={
                pendingAction?.action === "revoke" ? "destructive" : "default"
              }
              onClick={() => void confirmPendingAction()}
            >
              {pendingAction?.action === "revoke"
                ? "確認撤銷"
                : "重新產生新 QR"}
            </Button>
          </div>
        </Dialog>
      ) : null}
    </section>
  );
}
