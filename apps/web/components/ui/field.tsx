import React from "react";
import type { HTMLAttributes } from "react";
import { cn } from "../../lib/utils";

export function Field({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("ui-field", className)} {...props} />;
}
