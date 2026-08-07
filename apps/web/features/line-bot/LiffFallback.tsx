"use client";

import { useState } from "react";
import React from "react";

export function LiffFallback() {
  const [note, setNote] = useState("");
  return (
    <section aria-labelledby="liff-fallback-title">
      <h2 id="liff-fallback-title">補充回報</h2>
      <p>LINE Bot 無法完成時，可以在此修改多個答案或輸入較長心得。</p>
      <label>
        補充心得（選填）
        <textarea
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      <p aria-live="polite">{note.length} 字</p>
    </section>
  );
}
