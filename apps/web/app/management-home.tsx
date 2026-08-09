"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authFetch, clearAuth, getAccessToken } from "../lib/auth";

type Animal = { id: string; name: string };

export default function ManagementHome() {
  const router = useRouter();
  const [message, setMessage] = useState("正在載入 ORG-A 的動物…");

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }

    let cancelled = false;
    void authFetch("/v1/animals?page=1&page_size=1")
      .then(async (response) => {
        if (response.status === 401 || response.status === 409) {
          clearAuth();
          router.replace("/login");
          return;
        }
        if (!response.ok) {
          throw new Error(`無法載入動物（HTTP ${response.status}）`);
        }
        const data = (await response.json()) as { items: Animal[] };
        if (cancelled) return;
        const animal = data.items[0];
        if (!animal) {
          setMessage("ORG-A 目前沒有可查看的動物。");
          return;
        }
        router.replace(`/animals/${animal.id}/timeline`);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setMessage(
            error instanceof Error ? error.message : "管理首頁載入失敗",
          );
        }
      });

    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <main aria-labelledby="management-home-title">
      <h1 id="management-home-title">浪浪森友會</h1>
      <p>{message}</p>
    </main>
  );
}
