"use client";

import React, { useEffect, useState } from "react";
import { authFetch } from "../../../../lib/auth";
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
import { Field } from "../../../../components/ui/field";
import { Input } from "../../../../components/ui/input";
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
  token: string | null;
};

type PendingQrAction = {
  id: string;
  animalId: string;
  action: "revoke" | "regenerate";
};

export default function QrCodesPage() {
  const [items, setItems] = useState<Qr[]>([]);
  const [animalId, setAnimalId] = useState("");
  const [issuedToken, setIssuedToken] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [pendingAction, setPendingAction] = useState<PendingQrAction | null>(
    null,
  );
  const load = () => {
    setLoading(true);
    void authFetch("/v1/management/qr-codes")
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`QR 清單載入失敗（HTTP ${response.status}）`);
        setItems(((await response.json()) as { items: Qr[] }).items);
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
  const create = async () => {
    setError("");
    const response = await authFetch("/v1/management/qr-codes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ animal_id: animalId }),
    });
    if (!response.ok) {
      setError(`QR 建立失敗（HTTP ${response.status}）`);
      return;
    }
    const value = (await response.json()) as Qr;
    setIssuedToken(value.token ?? "");
    setAnimalId("");
    load();
  };
  const revoke = async (id: string) => {
    setError("");
    const response = await authFetch(`/v1/management/qr-codes/${id}/revoke`, {
      method: "POST",
    });
    if (!response.ok) setError(`QR 撤銷失敗（HTTP ${response.status}）`);
    else {
      setMessage("QR 已撤銷，既有 Token 已失效。");
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
    const value = (await response.json()) as Qr;
    setIssuedToken(value.token ?? "");
    setMessage("QR 已重新產生，既有 Token 已失效。");
    load();
  };

  const confirmPendingAction = async () => {
    const action = pendingAction;
    if (!action) return;
    setPendingAction(null);
    if (action.action === "revoke") await revoke(action.id);
    else await regenerate(action.id);
  };
  const print = () => {
    if (typeof window !== "undefined") window.print();
  };
  return (
    <section aria-labelledby="qr-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">QR BINDINGS</span>
          <h1 id="qr-title">QR 綁定</h1>
          <p>QR 只提供動物候選查詢，不是授權憑證；Token 僅在建立時顯示一次。</p>
        </div>
      </div>
      {error ? <Alert role="alert">{error}</Alert> : null}
      {message ? <Toast>{message}</Toast> : null}
      {issuedToken ? (
        <Alert role="status">
          請立即保存此一次性 Token：<code>{issuedToken}</code>
        </Alert>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>建立 QR</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="p1-actions">
            <Field>
              <label htmlFor="qr-animal">Animal ID</label>
              <Input
                id="qr-animal"
                value={animalId}
                onChange={(event) => setAnimalId(event.target.value)}
                placeholder="UUID"
              />
            </Field>
            <Button
              type="button"
              disabled={!animalId}
              onClick={() => void create()}
            >
              建立 QR
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>已建立綁定</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <LoadingState title="正在載入 QR…" />
          ) : items.length === 0 ? (
            <p className="muted">目前沒有 QR 綁定。</p>
          ) : (
            <Table>
              <TableHeader>
                <tr>
                  <TableHead>動物</TableHead>
                  <TableHead>狀態</TableHead>
                  <TableHead>Deep Link</TableHead>
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
                    <TableCell>{item.deep_link ?? "—"}</TableCell>
                    <TableCell>
                      <div className="p1-actions">
                        <Button
                          variant="destructive"
                          type="button"
                          disabled={item.revoked}
                          onClick={() =>
                            setPendingAction({
                              id: item.id,
                              animalId: item.animal_id,
                              action: "revoke",
                            })
                          }
                        >
                          撤銷
                        </Button>
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
                          重新產生
                        </Button>
                        <Button
                          variant="secondary"
                          type="button"
                          onClick={print}
                        >
                          列印
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <Dialog
        open={pendingAction !== null}
        role="alertdialog"
        title={
          pendingAction?.action === "revoke" ? "確認撤銷 QR" : "確認重新產生 QR"
        }
        onClose={() => setPendingAction(null)}
      >
        <p className="dialog-description">
          動物：{pendingAction?.animalId ?? "未知動物"}。這會讓目前綁定的 QR
          與既有 Token 立即失效，已發出的連結無法再使用。
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
            {pendingAction?.action === "revoke" ? "確認撤銷" : "確認重新產生"}
          </Button>
        </div>
      </Dialog>
    </section>
  );
}
