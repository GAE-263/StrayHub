import React, { forwardRef } from "react";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

type Variant = "default" | "secondary" | "ghost" | "destructive" | "link";

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }
>(function Button({ className, variant = "default", ...props }, ref) {
  return (
    <button
      ref={ref}
      className={cn("ui-button", `ui-button-${variant}`, className)}
      {...props}
    />
  );
});
