import React from "react";

export function Spinner({ label = "載入中" }: { label?: string }) {
  return <span className="ui-spinner" role="status" aria-label={label} />;
}
