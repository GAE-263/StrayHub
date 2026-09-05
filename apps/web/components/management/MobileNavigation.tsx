"use client";

import { useRef, useState } from "react";
import { LogOut } from "lucide-react";
import { iconMap } from "./icon-map";
import { NavigationLinks } from "./AppSidebar";
import { Button } from "../ui/button";
import { Sheet } from "../ui/sheet";

export function MobileNavigation({
  role,
  publicManagement = false,
  onLogout,
}: {
  role: string;
  publicManagement?: boolean;
  onLogout: () => void;
}) {
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
      </button>
      <Sheet open={open} title="管理工作台導覽" onClose={close}>
        <NavigationLinks
          role={role}
          publicManagement={publicManagement}
          onNavigate={close}
        />
        <div className="mobile-navigation-footer">
          <Button
            className="mobile-navigation-logout"
            variant="ghost"
            type="button"
            aria-label="登出管理工作台"
            onClick={onLogout}
          >
            <LogOut size={18} aria-hidden="true" />
            登出
          </Button>
        </div>
      </Sheet>
    </div>
  );
}
