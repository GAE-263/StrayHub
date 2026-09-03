"use client";

import React, { useEffect, useRef, useState } from "react";
import { authFetch } from "../../lib/auth";

type PhotoState = "loading" | "ready" | "error";

export function AnimalPhoto({
  photoUrl,
  alt,
  className,
}: {
  photoUrl: string;
  alt: string;
  className?: string;
}) {
  const [state, setState] = useState<PhotoState>("loading");
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const currentObjectUrl = useRef<string | null>(null);

  function releaseObjectUrl() {
    if (!currentObjectUrl.current) return;
    URL.revokeObjectURL(currentObjectUrl.current);
    currentObjectUrl.current = null;
  }

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    releaseObjectUrl();
    setObjectUrl(null);
    setState("loading");

    void authFetch(photoUrl, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("animal photo unavailable");
        const blob = await response.blob();
        if (!current || controller.signal.aborted) return;
        const nextUrl = URL.createObjectURL(blob);
        if (!current || controller.signal.aborted) {
          URL.revokeObjectURL(nextUrl);
          return;
        }
        currentObjectUrl.current = nextUrl;
        setObjectUrl(nextUrl);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (!current || controller.signal.aborted) return;
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setState("error");
      });

    return () => {
      current = false;
      controller.abort();
      releaseObjectUrl();
    };
  }, [photoUrl]);

  if (state === "ready" && objectUrl) {
    return (
      <img
        className={className}
        src={objectUrl}
        alt={alt}
        onError={() => {
          releaseObjectUrl();
          setObjectUrl(null);
          setState("error");
        }}
      />
    );
  }

  if (state === "error") {
    return <span className="muted">照片暫時無法顯示</span>;
  }

  return <span className="muted">正在安全載入照片…</span>;
}
