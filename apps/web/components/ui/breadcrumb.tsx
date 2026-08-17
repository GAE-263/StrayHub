import type { HTMLAttributes } from "react";
import { cn } from "../../lib/utils";

export function Breadcrumb({
  className,
  ...props
}: HTMLAttributes<HTMLElement>) {
  return (
    <nav
      aria-label="Breadcrumb"
      className={cn("ui-breadcrumb", className)}
      {...props}
    />
  );
}
