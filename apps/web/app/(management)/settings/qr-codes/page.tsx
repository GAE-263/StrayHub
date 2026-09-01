"use client";

import Link from "next/link";
import React, { useEffect, useState } from "react";
import { authFetch, type CurrentUser } from "../../../../lib/auth";
import { canManageCareQr } from "../../../../lib/management-capabilities";
import {
  formatQrCreatedAt,
  isActiveQr,
  qrStatusLabel,
  type ManagementQrCodeList,
  type ManagementQrCodeListItem,
} from "../../../../lib/qr-management";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PermissionDeniedState,
} from "../../../../components/management/StateViews";
import { statusLabel } from "../../../../components/management/ui-status";
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
import styles from "./qr-codes.module.css";

const QR_LIST_PATH = "/v1/management/qr-codes?status=all&page=1&page_size=20";

type PendingQrAction = {
  id: string;
  animalName: string;
  action: "revoke" | "regenerate";
};

function AnimalProfileLink({ item }: { item: ManagementQrCodeListItem }) {
  return (
    <Link className={styles.animalLink} href={`/animals/${item.animal_id}`}>
      {item.animal_name}
    </Link>
  );
}

export default function QrCodesPage() {
  const [data, setData] = useState<ManagementQrCodeList | null>(null);
  const [canManage, setCanManage] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [pendingAction, setPendingAction] = useState<PendingQrAction | null>(
    null,
  );

  const load = () => {
    setLoading(true);
    setLoadError("");
    setActionError("");
    setCanManage(false);
    setPermissionDenied(false);
    void Promise.all([
      authFetch(QR_LIST_PATH),
      authFetch("/v1/auth/active-shelter-context"),
      authFetch("/v1/auth/me"),
    ])
      .then(async ([qrResponse, contextResponse, profileResponse]) => {
        if (qrResponse.status === 403) {
          setData(null);
          setPermissionDenied(true);
          return;
        }
        if (!qrResponse.ok)
          throw new Error(`QR 清單載入失敗（HTTP ${qrResponse.status}）`);
        if (!contextResponse.ok || !profileResponse.ok)
          throw new Error("QR 管理權限載入失敗");
        const context = (await contextResponse.json()) as {
          organization_id: string;
        };
        const profile = (await profileResponse.json()) as CurrentUser;
        setData((await qrResponse.json()) as ManagementQrCodeList);
        setCanManage(canManageCareQr(profile, context.organization_id));
      })
      .catch((requestError: unknown) => {
        setData(null);
        setLoadError(
          requestError instanceof Error
            ? requestError.message
            : "QR 清單載入失敗",
        );
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const revoke = async (id: string) => {
    setActionError("");
    setMessage("");
    const response = await authFetch(`/v1/management/qr-codes/${id}/revoke`, {
      method: "POST",
    });
    if (!response.ok) setActionError(`QR 撤銷失敗（HTTP ${response.status}）`);
    else {
      setMessage("QR 已撤銷，已張貼的舊標籤無法再使用。");
      load();
    }
  };

  const regenerate = async (id: string) => {
    setActionError("");
    setMessage("");
    const response = await authFetch(
      `/v1/management/qr-codes/${id}/regenerate`,
      { method: "POST" },
    );
    if (!response.ok) {
      setActionError(`QR 重新產生失敗（HTTP ${response.status}）`);
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

  const items = data?.items ?? [];

  return (
    <section aria-labelledby="qr-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">CARE QR MANAGEMENT</span>
          <h1 id="qr-title">照護 QR 管理</h1>
          <p>辨識動物與 QR 狀態，安全處理重新列印、重新產生與撤銷。</p>
          <p className={`${styles.scopeNote} muted`}>
            僅顯示目前操作收容所的 QR 紀錄。
          </p>
        </div>
      </div>
      {actionError ? <Alert role="alert">{actionError}</Alert> : null}
      {message ? <Toast>{message}</Toast> : null}
      <Card>
        <CardHeader className={styles.listHeader}>
          <CardTitle>QR 紀錄</CardTitle>
          {!loading && data ? <p>共 {data.total} 筆</p> : null}
        </CardHeader>
        <CardContent>
          {loading ? (
            <LoadingState title="正在載入 QR…" />
          ) : permissionDenied ? (
            <PermissionDeniedState description="你沒有查看目前收容所 QR 紀錄的權限。" />
          ) : loadError ? (
            <ErrorState
              title="QR 清單載入失敗"
              description={loadError}
              action={
                <Button type="button" variant="secondary" onClick={load}>
                  重新載入
                </Button>
              }
            />
          ) : items.length === 0 ? (
            <EmptyState
              title="目前收容所尚無照護 QR 紀錄。"
              description="請前往動物檔案建立照護 QR。"
            />
          ) : (
            <>
              <ul className={styles.recordList} aria-label="照護 QR 紀錄">
                {items.map((item) => {
                  const activeQr = isActiveQr(item);
                  const activeAnimal = item.animal_status === "active";
                  return (
                    <li
                      className={`${styles.record} ${activeQr ? "" : styles.recordRevoked}`}
                      key={item.id}
                    >
                      <div className={styles.identity}>
                        <div className={styles.titleRow}>
                          <h3>
                            <AnimalProfileLink item={item} />
                          </h3>
                          <Badge
                            className={activeQr ? "" : styles.qrBadgeRevoked}
                          >
                            QR {qrStatusLabel(item)}
                          </Badge>
                        </div>
                        <p className={styles.location}>
                          <span>
                            收容編號：{item.shelter_number ?? "未提供"}
                          </span>
                          <span aria-hidden="true">·</span>
                          <span>區域：{item.area_name ?? "未分配"}</span>
                        </p>
                      </div>
                      <dl className={styles.metadata}>
                        <div>
                          <dt>動物狀態</dt>
                          <dd>
                            <Badge
                              className={
                                activeAnimal ? "" : styles.animalInactiveBadge
                              }
                            >
                              {statusLabel(item.animal_status)}
                            </Badge>
                          </dd>
                        </div>
                        <div>
                          <dt>建立時間</dt>
                          <dd>
                            <time dateTime={item.created_at}>
                              {formatQrCreatedAt(item.created_at)}
                            </time>
                          </dd>
                        </div>
                      </dl>
                      <div className={`p1-actions ${styles.actions}`}>
                        {activeQr && activeAnimal ? (
                          <>
                            {item.deep_link ? (
                              <Link
                                className="ui-button ui-button-secondary"
                                href={`/animals/${item.animal_id}`}
                              >
                                前往重新列印
                              </Link>
                            ) : (
                              <span className={styles.legacyNote}>
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
                                      animalName: item.animal_name,
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
                                      animalName: item.animal_name,
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
                          <>
                            <Link
                              className="ui-button ui-button-secondary"
                              href={`/animals/${item.animal_id}`}
                            >
                              前往動物檔案
                            </Link>
                            {activeQr && canManage ? (
                              <Button
                                variant="destructive"
                                type="button"
                                onClick={() =>
                                  setPendingAction({
                                    id: item.id,
                                    animalName: item.animal_name,
                                    action: "revoke",
                                  })
                                }
                              >
                                撤銷 QR
                              </Button>
                            ) : null}
                          </>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
              {data && data.total > items.length ? (
                <Alert className={styles.pageNotice}>
                  目前顯示前 {items.length} 筆 QR
                  紀錄；完整分頁將於後續管理功能提供。
                </Alert>
              ) : null}
            </>
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
            動物：{pendingAction?.animalName ?? "未知動物"}。
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
