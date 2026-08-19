"use client";

import React, { FormEvent, useCallback, useEffect, useState } from "react";
import { AnimalConfirmationCard } from "../../../features/animal-selection/AnimalConfirmationCard";
import { Button } from "../../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../components/ui/card";
import { Field } from "../../../components/ui/field";
import { Input } from "../../../components/ui/input";

type AnimalCandidate = {
  id: string;
  name: string;
  shelter_number: string | null;
  photo_url?: string | null;
  cage?: string | null;
  area?: string | null;
  organization_id: string;
  can_report: boolean;
};

type AnimalConfirmation = AnimalCandidate & { confirmation_token: string };

async function responseData<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = "動物查詢失敗";
    try {
      const body = (await response.json()) as { message?: string };
      message = body.message ?? message;
    } catch {
      // Keep a safe generic error when the server response is not JSON.
    }
    throw new Error(`${response.status}: ${message}`);
  }
  return response.json() as Promise<T>;
}

export default function AnimalConfirmationPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
  const [candidates, setCandidates] = useState<AnimalCandidate[]>([]);
  const [selected, setSelected] = useState<AnimalConfirmation | null>(null);
  const [query, setQuery] = useState("");
  const [qrToken, setQrToken] = useState("");
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const request = useCallback(
    async <T,>(path: string, init?: RequestInit) => {
      const token = window.sessionStorage.getItem("access_token");
      const headers = new Headers(init?.headers);
      headers.set("Content-Type", "application/json");
      if (token) headers.set("Authorization", `Bearer ${token}`);
      return responseData<T>(
        await fetch(`${apiBaseUrl}${path}`, { ...init, headers }),
      );
    },
    [apiBaseUrl],
  );

  const loadToday = useCallback(async () => {
    const data = await request<{ items: AnimalCandidate[] }>("/v1/animals");
    setCandidates(data.items);
  }, [request]);

  useEffect(() => {
    void loadToday().catch((error: Error) => setErrorMessage(error.message));
    const token = new URLSearchParams(window.location.search).get("qr_token");
    if (token) setQrToken(token);
  }, [loadToday]);

  const run = async (action: () => Promise<void>) => {
    setErrorMessage("");
    setMessage("");
    try {
      await action();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "操作失敗");
    }
  };

  const search = async (event: FormEvent) => {
    event.preventDefault();
    await run(async () => {
      const data = await request<{ items: AnimalCandidate[] }>(
        `/v1/animals/search?query=${encodeURIComponent(query)}`,
      );
      setCandidates(data.items);
      setSelected(null);
    });
  };

  const resolveQr = async (event: FormEvent) => {
    event.preventDefault();
    await run(async () => {
      const candidate = await request<AnimalCandidate>(
        "/v1/qr-tokens/resolve",
        {
          method: "POST",
          body: JSON.stringify({ qr_token: qrToken }),
        },
      );
      setCandidates([candidate]);
      setSelected(null);
      setMessage("QR Code 已解析，請確認動物身分。");
    });
  };

  const selectCandidate = async (candidate: AnimalCandidate) => {
    await run(async () => {
      const confirmed = await request<AnimalConfirmation>(
        `/v1/animals/${candidate.id}/confirm`,
        { method: "POST" },
      );
      setSelected(confirmed);
    });
  };

  const createDraft = async () => {
    if (!selected) return;
    await run(async () => {
      const draft = await request<{ id: string }>("/v1/care-report-drafts", {
        method: "POST",
        body: JSON.stringify({
          animal_id: selected.id,
          confirmation_token: selected.confirmation_token,
        }),
      });
      setMessage(`已建立回報草稿：${draft.id}`);
    });
  };

  return (
    <main
      className="volunteer-page"
      aria-labelledby="animal-confirmation-title"
    >
      <div className="volunteer-page-heading">
        <span className="eyebrow">VOLUNTEER CARE</span>
        <h1 id="animal-confirmation-title">選擇照護動物</h1>
        <p>請先從今日名單、QR Code 或收容編號找到候選動物，再明確確認。</p>
      </div>
      {errorMessage && (
        <p className="notice error" role="alert">
          {errorMessage}
        </p>
      )}
      {message && (
        <p className="notice success" role="status" aria-live="polite">
          {message}
        </p>
      )}

      <div className="volunteer-search-grid">
        <Card
          className="volunteer-search-card"
          aria-labelledby="qr-search-title"
        >
          <CardHeader>
            <CardTitle id="qr-search-title">QR Code</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="volunteer-search-form"
              aria-label="qr-search-form"
              onSubmit={(event) => void resolveQr(event)}
            >
              <Field>
                <label htmlFor="qr-token">QR Token</label>
                <Input
                  id="qr-token"
                  value={qrToken}
                  onChange={(event) => setQrToken(event.target.value)}
                  required
                />
              </Field>
              <Button type="submit">解析 QR Code</Button>
            </form>
          </CardContent>
        </Card>

        <Card
          className="volunteer-search-card"
          aria-labelledby="shelter-number-search-title"
        >
          <CardHeader>
            <CardTitle id="shelter-number-search-title">收容編號搜尋</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="volunteer-search-form"
              aria-label="shelter-number-search-form"
              onSubmit={(event) => void search(event)}
            >
              <Field>
                <label htmlFor="shelter-number-query">完整或部分收容編號</label>
                <Input
                  id="shelter-number-query"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  required
                />
              </Field>
              <Button type="submit">搜尋</Button>
            </form>
          </CardContent>
        </Card>
      </div>

      <Card
        className="volunteer-candidates-card"
        aria-labelledby="today-list-title"
      >
        <CardHeader>
          <CardTitle id="today-list-title">今日可回報動物</CardTitle>
        </CardHeader>
        <CardContent>
          {candidates.length === 0 ? (
            <p>目前沒有可回報的動物。</p>
          ) : (
            <ul className="volunteer-candidate-list">
              {candidates.map((candidate) => (
                <li
                  className="volunteer-candidate-item list-card"
                  key={candidate.id}
                >
                  <span>
                    {candidate.name}／{candidate.shelter_number ?? "未維護"}
                  </span>
                  <Button
                    variant="secondary"
                    type="button"
                    onClick={() => void selectCandidate(candidate)}
                  >
                    查看確認卡
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {selected && (
        <AnimalConfirmationCard
          animal={{
            id: selected.id,
            name: selected.name,
            shelterNumber: selected.shelter_number,
            photoUrl: selected.photo_url,
            cage: selected.cage,
            area: selected.area,
            canReport: selected.can_report,
          }}
          onConfirm={() => void createDraft()}
          onReselect={() => setSelected(null)}
        />
      )}
    </main>
  );
}
