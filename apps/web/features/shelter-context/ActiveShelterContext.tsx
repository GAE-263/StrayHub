"use client";

import React from "react";

type Props = { organizationName: string; onSwitch: () => void };

export function ActiveShelterContext({ organizationName, onSwitch }: Props) {
  return (
    <section aria-label="目前收容所">
      <span>目前操作收容所：{organizationName}</span>
      <button type="button" onClick={onSwitch}>
        切換收容所
      </button>
    </section>
  );
}
