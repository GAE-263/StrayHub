"use client";

import Link from "next/link";
import { LogOut } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../ui/button";
import { Select } from "../ui/select";

type Props = {
  displayName: string;
  organizationLabel: string;
  organizations: Array<{ id: string; code: string; name: string }>;
  activeOrganizationId: string;
  onSwitchOrganization: (organizationId: string) => void;
  onLogout: () => void;
  mobileNavigation?: ReactNode;
};

export function AppHeader({
  displayName,
  organizationLabel,
  organizations,
  activeOrganizationId,
  onSwitchOrganization,
  onLogout,
  mobileNavigation,
}: Props) {
  return (
    <header className="app-header">
      <div className="header-brand-group">
        {mobileNavigation}
        <Link className="brand" href="/" aria-label="回到管理首頁">
          <span className="brand-mark">森</span>
          <span>
            <strong>浪浪森友會</strong>
            <small>CRM 管理工作台</small>
          </span>
        </Link>
      </div>
      <div className="header-context">
        {organizations.length > 1 ? (
          <label className="context-selector">
            <span className="sr-only">切換目前收容所</span>
            <Select
              className="context-select"
              aria-label="切換目前收容所"
              value={activeOrganizationId}
              onChange={(event) => onSwitchOrganization(event.target.value)}
            >
              {organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.name}（{organization.code}）
                </option>
              ))}
            </Select>
          </label>
        ) : (
          <span className="context-pill" aria-label="目前收容所">
            {organizationLabel}
          </span>
        )}
        <span className="user-label">{displayName}</span>
        <Button
          className="button-quiet header-logout"
          variant="ghost"
          type="button"
          aria-label="登出管理工作台"
          onClick={onLogout}
        >
          <LogOut size={16} aria-hidden="true" />
          登出
        </Button>
      </div>
    </header>
  );
}
