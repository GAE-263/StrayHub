"use client";

import Link from "next/link";
import React, { useEffect, useRef, useState } from "react";
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
import { Field } from "../../../../components/ui/field";
import { Input } from "../../../../components/ui/input";
import { Select } from "../../../../components/ui/select";
import { Toast } from "../../../../components/ui/toast";
import { buildQrCodesQuery, type QrStatusFilter } from "../../management-query";
import styles from "./qr-codes.module.css";

const SEARCH_DEBOUNCE_MS = 300;
const PAGE_SIZE = 20;

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
  const [inputQuery, setInputQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [status, setStatus] = useState<QrStatusFilter>("all");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ManagementQrCodeList | null>(null);
  const [dataKey, setDataKey] = useState("");
  const [canManage, setCanManage] = useState(false);
  const [listError, setListError] = useState("");
  const [capabilityError, setCapabilityError] = useState("");
  const [actionError, setActionError] = useState("");
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(true);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [capabilityRefresh, setCapabilityRefresh] = useState(0);
  const [pendingAction, setPendingAction] = useState<PendingQrAction | null>(
    null,
  );
  const latestListRequest = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const normalized = inputQuery.trim();
      setPage(1);
      setDebouncedQuery(normalized);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [inputQuery]);

  useEffect(() => {
    const controller = new AbortController();
    setCapabilitiesLoading(true);
    setCapabilityError("");
    setCanManage(false);
    void Promise.all([
      authFetch("/v1/auth/active-shelter-context", {
        signal: controller.signal,
      }),
      authFetch("/v1/auth/me", { signal: controller.signal }),
    ])
      .then(async ([contextResponse, profileResponse]) => {
        if (!contextResponse.ok || !profileResponse.ok)
          throw new Error("QR 管理權限載入失敗");
        const context = (await contextResponse.json()) as {
          organization_id: string;
        };
        const profile = (await profileResponse.json()) as CurrentUser;
        if (!controller.signal.aborted)
          setCanManage(canManageCareQr(profile, context.organization_id));
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted)
          setCapabilityError(
            requestError instanceof Error
              ? requestError.message
              : "QR 管理權限載入失敗",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setCapabilitiesLoading(false);
      });
    return () => controller.abort();
  }, [capabilityRefresh]);

  const requestKey = `${debouncedQuery}\u0000${status}\u0000${page}\u0000${PAGE_SIZE}\u0000${refreshVersion}`;

  useEffect(() => {
    const controller = new AbortController();
    const requestGeneration = ++latestListRequest.current;
    const params = buildQrCodesQuery({
      page,
      pageSize: PAGE_SIZE,
      query: debouncedQuery,
      status,
    });
    let reconcilingPage = false;
    const isCurrent = () =>
      !controller.signal.aborted &&
      requestGeneration === latestListRequest.current;

    setLoading(true);
    setListError("");
    setActionError("");
    setPermissionDenied(false);
    void authFetch(`/v1/management/qr-codes?${params}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 403) {
          if (!isCurrent()) return;
          setData(null);
          setPermissionDenied(true);
          return;
        }
        if (!response.ok)
          throw new Error(`QR 清單載入失敗（HTTP ${response.status}）`);
        const nextData = (await response.json()) as ManagementQrCodeList;
        if (!isCurrent()) return;
        const lastPage = Math.max(
          1,
          Math.ceil(nextData.total / nextData.page_size),
        );
        if (nextData.items.length === 0 && page > lastPage) {
          reconcilingPage = true;
          setPage(lastPage);
          return;
        }
        setData(nextData);
        setDataKey(requestKey);
      })
      .catch((requestError: unknown) => {
        if (!isCurrent()) return;
        setData(null);
        setListError(
          requestError instanceof Error
            ? requestError.message
            : "QR 清單載入失敗",
        );
      })
      .finally(() => {
        if (isCurrent() && !reconcilingPage) setLoading(false);
      });
    return () => controller.abort();
  }, [debouncedQuery, page, refreshVersion, requestKey, status]);

  const refreshList = () => setRefreshVersion((value) => value + 1);
  const retry = () => {
    setCapabilityRefresh((value) => value + 1);
    refreshList();
  };

  const performMutation = async (
    id: string,
    action: PendingQrAction["action"],
  ) => {
    setActionError("");
    setMessage("");
    try {
      const response = await authFetch(
        `/v1/management/qr-codes/${id}/${action}`,
        { method: "POST" },
      );
      if (!response.ok)
        throw new Error(
          `QR ${action === "revoke" ? "撤銷" : "重新產生"}失敗（HTTP ${response.status}）`,
        );
      await response.json();
      setMessage(
        action === "revoke"
          ? "QR 已撤銷，已張貼的舊標籤無法再使用。"
          : "QR 已重新產生，請至動物檔案列印並更換舊標籤。",
      );
      refreshList();
    } catch (requestError: unknown) {
      setActionError(
        requestError instanceof Error
          ? requestError.message
          : action === "revoke"
            ? "QR 撤銷失敗"
            : "QR 重新產生失敗",
      );
    }
  };

  const confirmPendingAction = async () => {
    const action = pendingAction;
    if (!action) return;
    setPendingAction(null);
    await performMutation(action.id, action.action);
  };

  const resetFilters = () => {
    setInputQuery("");
    setDebouncedQuery("");
    setStatus("all");
    setPage(1);
  };

  const searchPending = inputQuery.trim() !== debouncedQuery;
  const resultsPending =
    searchPending ||
    loading ||
    capabilitiesLoading ||
    (!listError &&
      !permissionDenied &&
      !capabilityError &&
      dataKey !== requestKey);
  const displayError = listError || capabilityError;
  const items = data?.items ?? [];
  const filtered = Boolean(debouncedQuery) || status !== "all";
  const showPagination =
    data !== null && (data.total > data.page_size || data.page > 1);

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
          {!resultsPending && data ? <p>共 {data.total} 筆</p> : null}
        </CardHeader>
        <CardContent>
          <div className={styles.controls} aria-label="QR 紀錄篩選">
            <Field className={styles.searchField}>
              <label htmlFor="qr-query">搜尋</label>
              <Input
                id="qr-query"
                type="search"
                value={inputQuery}
                onChange={(event) => setInputQuery(event.target.value)}
                placeholder="搜尋動物名稱或收容編號"
              />
            </Field>
            <Field className={styles.statusField}>
              <label htmlFor="qr-status">QR 狀態</label>
              <Select
                id="qr-status"
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value as QrStatusFilter);
                  setPage(1);
                }}
              >
                <option value="all">全部</option>
                <option value="active">使用中</option>
                <option value="revoked">已撤銷</option>
              </Select>
            </Field>
            <Button
              className={styles.resetButton}
              type="button"
              variant="ghost"
              disabled={!inputQuery.trim() && status === "all"}
              onClick={resetFilters}
            >
              重設篩選
            </Button>
          </div>
          {resultsPending ? (
            <LoadingState
              title={searchPending ? "正在準備搜尋…" : "正在載入 QR…"}
            />
          ) : permissionDenied ? (
            <PermissionDeniedState description="你沒有查看目前收容所 QR 紀錄的權限。" />
          ) : displayError ? (
            <ErrorState
              title="QR 清單載入失敗"
              description={displayError}
              action={
                <Button type="button" variant="secondary" onClick={retry}>
                  重新載入
                </Button>
              }
            />
          ) : items.length === 0 ? (
            filtered ? (
              <EmptyState
                title="找不到符合條件的 QR 紀錄。"
                description="請調整搜尋或 QR 狀態篩選。"
                action={
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={resetFilters}
                  >
                    重設篩選
                  </Button>
                }
              />
            ) : (
              <EmptyState
                title="目前收容所尚無照護 QR 紀錄。"
                description="請前往動物檔案建立照護 QR。"
              />
            )
          ) : (
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
                        <span>收容編號：{item.shelter_number ?? "未提供"}</span>
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
          )}
          {showPagination && data ? (
            <nav className={styles.pagination} aria-label="QR 紀錄分頁">
              <Button
                variant="secondary"
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((value) => Math.max(1, value - 1))}
              >
                上一頁
              </Button>
              <span className="muted" role="status" aria-live="polite">
                {resultsPending
                  ? `正在載入第 ${page} 頁…`
                  : `第 ${data.page} 頁，共 ${data.total} 筆`}
              </span>
              <Button
                variant="secondary"
                type="button"
                disabled={page * data.page_size >= data.total}
                onClick={() => setPage((value) => value + 1)}
              >
                下一頁
              </Button>
            </nav>
          ) : null}
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
