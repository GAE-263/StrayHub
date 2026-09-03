"use client";

import React, { useEffect, useRef, useState } from "react";
import { Image as ImageIcon } from "lucide-react";
import { fetchGrowthDiaryPhoto } from "./api";
import styles from "./growth-diary.module.css";

type PhotoState = "loading" | "ready" | "error";

export function DiaryPhoto({ entryId, alt }: { entryId: string; alt: string }) {
  const [photoState, setPhotoState] = useState<PhotoState>("loading");
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const objectUrl = useRef<string | null>(null);

  function releaseObjectUrl() {
    if (!objectUrl.current) return;
    URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = null;
  }

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    releaseObjectUrl();
    setPhotoUrl(null);
    setPhotoState("loading");

    void fetchGrowthDiaryPhoto(entryId, controller.signal)
      .then((blob) => {
        if (!current || controller.signal.aborted) return;
        const nextUrl = URL.createObjectURL(blob);
        if (!current || controller.signal.aborted) {
          URL.revokeObjectURL(nextUrl);
          return;
        }
        objectUrl.current = nextUrl;
        setPhotoUrl(nextUrl);
        setPhotoState("ready");
      })
      .catch((error: unknown) => {
        if (!current || controller.signal.aborted) return;
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setPhotoState("error");
      });

    return () => {
      current = false;
      controller.abort();
      releaseObjectUrl();
    };
  }, [entryId]);

  if (photoState === "ready" && photoUrl) {
    return (
      <div className={styles.photoFrame}>
        <img
          className={styles.diaryPhoto}
          src={photoUrl}
          alt={alt}
          onError={() => {
            releaseObjectUrl();
            setPhotoUrl(null);
            setPhotoState("error");
          }}
        />
      </div>
    );
  }

  return (
    <div
      className={styles.photoFallback}
      role={photoState === "error" ? "alert" : "status"}
    >
      <ImageIcon size={22} aria-hidden="true" />
      <span>
        {photoState === "error" ? "照片暫時無法顯示" : "正在安全載入照片…"}
      </span>
    </div>
  );
}
