"use client";

import { useRef, useState } from "react";
import { iconMap } from "./icon-map";
import { NavigationLinks } from "./AppSidebar";
import { Sheet } from "../ui/sheet";

export function MobileNavigation({ role }: { role: string }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const Menu = iconMap.menu;
  const close = () => {
    setOpen(false);
    window.requestAnimationFrame(() => triggerRef.current?.focus());
  };
  return (
    <div className="mobile-navigation">
      <button
        ref={triggerRef}
        className="mobile-menu-trigger"
        type="button"
        aria-label="開啟管理工作台導覽"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        <Menu size={20} aria-hidden="true" />
        <span>導覽</span>
      </button>
      <Sheet open={open} title="管理工作台導覽" onClose={close}>
        <NavigationLinks role={role} onNavigate={close} />
      </Sheet>
    </div>
  );
}
