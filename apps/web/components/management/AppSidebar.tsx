"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { iconMap, type IconName } from "./icon-map";
import { Sidebar } from "../ui/sidebar";
import { canReviewVolunteerApplications } from "../../lib/management-capabilities";

type Item = { href: string; label: string; roles?: string[]; icon?: IconName };

export const navigationGroups: Array<{ heading: string; links: Item[] }> = [
  {
    heading: "工作台",
    links: [
      { href: "/", label: "總覽", icon: "view" },
      { href: "/animals", label: "動物檔案", icon: "search" },
      { href: "/reports", label: "回報收件匣", icon: "audit" },
      { href: "/care-calendar", label: "照護行事曆", icon: "calendar" },
      { href: "/ai-review", label: "AI 人工覆核", icon: "ai" },
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
        label: "照護 QR 管理",
        roles: ["PLATFORM_ADMIN", "SHELTER_ADMIN"],
        icon: "access",
      },
      { href: "/settings/audit", label: "稽核紀錄", icon: "audit" },
      {
        href: "/volunteers/applications",
        label: "志工報名審核",
        roles: ["PLATFORM_ADMIN", "SHELTER_ADMIN"],
        icon: "access",
      },
      {
        href: "/volunteers/access",
        label: "志工授權管理",
        roles: ["PLATFORM_ADMIN", "SHELTER_ADMIN"],
        icon: "access",
      },
      {
        href: "/volunteers/notifications",
        label: "志工通知失敗",
        roles: ["PLATFORM_ADMIN", "SHELTER_ADMIN"],
        icon: "history",
      },
      {
        href: "/settings/volunteer-access",
        label: "志工授權設定",
        roles: ["PLATFORM_ADMIN", "SHELTER_ADMIN"],
        icon: "settings",
      },
      {
        href: "/shelters",
        label: "權限管理",
        roles: ["PLATFORM_ADMIN", "SHELTER_ADMIN"],
        icon: "history",
      },
      {
        href: "/platform-admins",
        label: "平台管理員",
        roles: ["PLATFORM_ADMIN"],
        icon: "settings",
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
            .filter(
              (link) =>
                !link.roles ||
                (link.href === "/volunteers/applications"
                  ? canReviewVolunteerApplications(role)
                  : link.roles.includes(role)),
            )
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
