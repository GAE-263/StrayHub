"use client";

import Link from "next/link";

type Props = {
  displayName: string;
  organizationLabel: string;
  organizations: Array<{ id: string; code: string; name: string }>;
  activeOrganizationId: string;
  onSwitchOrganization: (organizationId: string) => void;
  onLogout: () => void;
};

export function AppHeader({
  displayName,
  organizationLabel,
  organizations,
  activeOrganizationId,
  onSwitchOrganization,
  onLogout,
}: Props) {
  return (
    <header className="app-header">
      <Link className="brand" href="/" aria-label="回到管理首頁">
        <span className="brand-mark">森</span>
        <span>
          <strong>浪浪森友會</strong>
          <small>CRM 管理工作台</small>
        </span>
      </Link>
      <div className="header-context">
        {organizations.length > 1 ? (
          <label className="context-selector">
            <span className="sr-only">切換目前收容所</span>
            <select
              aria-label="切換目前收容所"
              value={activeOrganizationId}
              onChange={(event) => onSwitchOrganization(event.target.value)}
            >
              {organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.name}（{organization.code}）
                </option>
              ))}
            </select>
          </label>
        ) : (
          <span className="context-pill" aria-label="目前收容所">
            {organizationLabel}
          </span>
        )}
        <span className="user-label">{displayName}</span>
        <button
          className="button button-quiet"
          type="button"
          onClick={onLogout}
        >
          登出
        </button>
      </div>
    </header>
  );
}
