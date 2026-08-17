import React from "react";
import type { HTMLAttributes } from "react";
import { cn } from "../../lib/utils";

export function Sidebar({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <aside className={cn("ui-sidebar", className)} {...props} />;
}
