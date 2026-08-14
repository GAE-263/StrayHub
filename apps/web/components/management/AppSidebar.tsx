"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { iconMap, type IconName } from "./icon-map";
import { Sidebar } from "../ui/sidebar";

type Item = { href: string; label: string; roles?: string[]; icon?: IconName };

export const navigationGroups: Array<{ heading: string; links: Item[] }> = [
  {
    heading: "工作台",
    links: [
      { href: "/", label: "總覽", icon: "view" },
      { href: "/animals", label: "動物檔案", icon: "search" },
      { href: "/reports", label: "報告收件匣", icon: "audit" },
      { href: "/ai-review", label: "AI Review Queue", icon: "ai" },
    ],
  },
  {
    heading: "設定與治理",
    links: [
      {
        href: "/settings/observation-options",
        label: "觀察詞彙",
        icon: "settings",
      },
      {
        href: "/settings/reportable-scope",
        label: "可回報範圍",
        roles: ["PLATFORM_ADMIN", "SHELTER_ADMIN"],
        icon: "settings",
      },
      {
        href: "/settings/qr-codes",
        label: "QR 綁定",
        roles: ["PLATFORM_ADMIN", "SHELTER_ADMIN"],
        icon: "access",
      },
      { href: "/settings/audit", label: "Audit Query", icon: "audit" },
      {
        href: "/shelters",
        label: "收容所與 Membership",
        roles: ["PLATFORM_ADMIN", "SHELTER_ADMIN"],
        icon: "history",
      },
    ],
  },
];

export function NavigationLinks({
  role,
  onNavigate,
}: {
  role: string;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  return (
    <nav aria-label="管理工作台導航">
      {navigationGroups.map((group) => (
        <div className="nav-group" key={group.heading}>
          <span className="nav-heading">{group.heading}</span>
          {group.links
            .filter((link) => !link.roles || link.roles.includes(role))
            .map((link) => (
              <Link
                className={
                  pathname === link.href ||
                  (link.href !== "/" && pathname.startsWith(`${link.href}/`))
                    ? "nav-link active"
                    : "nav-link"
                }
                href={link.href}
                key={link.href}
                onClick={onNavigate}
              >
                {link.icon
                  ? (() => {
                      const Icon = iconMap[link.icon];
                      return <Icon size={16} aria-hidden="true" />;
                    })()
                  : null}
                {link.label}
              </Link>
            ))}
        </div>
      ))}
    </nav>
  );
}

export function AppSidebar({ role }: { role: string }) {
  return (
    <Sidebar className="app-sidebar" aria-label="管理工作台導航">
      <div className="sidebar-intro">
        <span className="eyebrow">ACTIVE WORKSPACE</span>
        <p>以動物為中心，串起回報、審核與照護決策。</p>
      </div>
      <NavigationLinks role={role} />
    </Sidebar>
  );
}
