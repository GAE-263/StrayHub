"use client";

import React from "react";

type Props = {
  organizationName: string;
  onSwitch: () => void;
  contextMismatch?: boolean;
};

export function ActiveShelterContext({
  organizationName,
  onSwitch,
  contextMismatch = false,
}: Props) {
  return (
    <section aria-label="目前收容所">
      <span>目前操作收容所：{organizationName}</span>
      {contextMismatch && (
        <p role="alert">目前頁面與操作中的收容所不一致，請先明確切換收容所。</p>
      )}
      <button type="button" onClick={onSwitch}>
        切換收容所
      </button>
    </section>
  );
}
