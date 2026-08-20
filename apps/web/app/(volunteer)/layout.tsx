"use client";

import React, { type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AuthenticatedRouteBoundary } from "../../components/auth/AuthenticatedRouteBoundary";

export default function VolunteerRouteLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();
  const router = useRouter();

  if (pathname === "/volunteer-entry") return children;

  return (
    <AuthenticatedRouteBoundary
      area="volunteer"
      pathname={pathname}
      onRedirect={(destination) => router.replace(destination)}
      onReenter={() => router.replace("/volunteer-entry")}
      onBack={() => router.back()}
    >
      {children}
    </AuthenticatedRouteBoundary>
  );
}
