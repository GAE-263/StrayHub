import React from "react";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

type Variant = "default" | "secondary" | "ghost" | "destructive" | "link";

export function Button({
  className,
  variant = "default",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={cn("ui-button", `ui-button-${variant}`, className)}
      {...props}
    />
  );
}
