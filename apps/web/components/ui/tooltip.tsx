import React from "react";
import type { ReactNode } from "react";

export function Tooltip({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <span className="ui-tooltip" title={label}>
      {children}
    </span>
  );
}
