"use client";

import { useEffect, useState } from "react";
import { authFetch } from "../../../../lib/auth";
import {
  ErrorState,
  LoadingState,
} from "../../../../components/management/StateViews";

type Qr = {
  id: string;
  animal_id: string;
  status: string;
  revoked: boolean;
  deep_link: string | null;
  token: string | null;
};

export default function QrCodesPage() {
  const [items, setItems] = useState<Qr[]>([]);
  const [animalId, setAnimalId] = useState("");
  const [issuedToken, setIssuedToken] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
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
    const response = await authFetch(`/v1/management/qr-codes/${id}/revoke`, {
      method: "POST",
    });
    if (!response.ok) setError(`QR 撤銷失敗（HTTP ${response.status}）`);
    else load();
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
    load();
  };
  const print = () => {
    if (typeof window !== "undefined") window.print();
  };
  return (
    <main aria-labelledby="qr-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">QR BINDINGS</span>
          <h1 id="qr-title">QR 綁定</h1>
          <p>QR 只提供動物候選查詢，不是授權憑證；Token 僅在建立時顯示一次。</p>
        </div>
      </div>
      {error ? <ErrorState title="QR 操作失敗" description={error} /> : null}
      {issuedToken ? (
        <p className="notice success" role="status">
          請立即保存此一次性 Token：<code>{issuedToken}</code>
        </p>
      ) : null}
      <section className="panel">
        <h2>建立 QR</h2>
        <div className="toolbar">
          <div className="field">
            <label htmlFor="qr-animal">Animal ID</label>
            <input
              id="qr-animal"
              value={animalId}
              onChange={(event) => setAnimalId(event.target.value)}
              placeholder="UUID"
            />
          </div>
          <button
            className="button"
            type="button"
            disabled={!animalId}
            onClick={() => void create()}
          >
            建立 QR
          </button>
        </div>
      </section>
      <section className="panel">
        <h2>已建立綁定</h2>
        {loading ? (
          <LoadingState title="正在載入 QR…" />
        ) : items.length === 0 ? (
          <p className="muted">目前沒有 QR 綁定。</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>動物</th>
                  <th>狀態</th>
                  <th>Deep Link</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.animal_id.slice(0, 8)}…</td>
                    <td>
                      <span className="badge">{item.status}</span>
                    </td>
                    <td>{item.deep_link ?? "—"}</td>
                    <td>
                      <button
                        className="button button-secondary"
                        type="button"
                        disabled={item.revoked}
                        onClick={() => void revoke(item.id)}
                      >
                        撤銷
                      </button>
                      <button
                        className="button button-secondary"
                        type="button"
                        onClick={() => void regenerate(item.id)}
                      >
                        重新產生
                      </button>
                      <button
                        className="button button-secondary"
                        type="button"
                        onClick={print}
                      >
                        列印
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
