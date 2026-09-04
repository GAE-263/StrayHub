"use client";

import React, { useEffect, useRef, useState } from "react";
import { authFetch } from "../../lib/auth";

type PhotoState = "loading" | "ready" | "error";

export function AnimalPhoto({
  photoUrl,
  alt,
  className,
}: {
  photoUrl?: string | null;
  alt: string;
  className?: string;
}) {
  const [state, setState] = useState<PhotoState>("loading");
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const container = useRef<HTMLSpanElement | null>(null);
  const currentObjectUrl = useRef<string | null>(null);

  function releaseObjectUrl() {
    if (!currentObjectUrl.current) return;
    URL.revokeObjectURL(currentObjectUrl.current);
    currentObjectUrl.current = null;
  }

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    let started = false;
    let observer: IntersectionObserver | null = null;
    releaseObjectUrl();
    setObjectUrl(null);
    setState("loading");

    const load = () => {
      if (started || !photoUrl) return;
      started = true;
      observer?.disconnect();
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
    };

    if (photoUrl) {
      if (typeof IntersectionObserver === "undefined" || !container.current) {
        load();
      } else {
        observer = new IntersectionObserver(
          (entries) => {
            if (entries.some((entry) => entry.isIntersecting)) load();
          },
          { rootMargin: "200px" },
        );
        observer.observe(container.current);
      }
    }

    return () => {
      current = false;
      observer?.disconnect();
      controller.abort();
      releaseObjectUrl();
    };
  }, [photoUrl]);

  if (!photoUrl) return null;

  if (state === "ready" && objectUrl) {
    return (
      <span ref={container} style={{ display: "inline-flex" }}>
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
      </span>
    );
  }

  if (state === "error") {
    return (
      <span ref={container} className="muted">
        照片暫時無法顯示
      </span>
    );
  }

  return (
    <span ref={container} className="muted">
      正在安全載入照片…
    </span>
  );
}
