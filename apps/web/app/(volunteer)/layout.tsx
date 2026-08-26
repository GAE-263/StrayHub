"use client";

import React, { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AuthenticatedRouteBoundary } from "../../components/auth/AuthenticatedRouteBoundary";
import { ProtectedRouteState } from "../../components/auth/ProtectedRouteState";
import { getSessionSource } from "../../lib/auth";
import {
  beginLiffRecovery,
  getLiffEntryReference,
} from "../../lib/liff-session";

export default function VolunteerRouteLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();
  const router = useRouter();
  const [recoveryPending, setRecoveryPending] = useState(false);
  useEffect(() => {
    if (pathname === "/volunteer-entry") setRecoveryPending(false);
  }, [pathname]);
  useEffect(() => {
    const recoverLiffSession = () => {
      const entry = getLiffEntryReference();
      if (getSessionSource() !== "liff" || !entry) {
        return;
      }
      setRecoveryPending(true);
      const recovery = beginLiffRecovery(pathname);
      if (recovery === "in-flight") return;
      if (recovery === "terminal" || recovery === "unavailable") {
        router.replace(
          `/volunteer-entry?entry=${encodeURIComponent(entry)}&recovery=terminal`,
        );
        return;
      }
      if (recovery !== "started") return;
      router.replace(
        `/volunteer-entry?entry=${encodeURIComponent(entry)}&recovery=exchange`,
      );
    };

    window.addEventListener("strayhub:liff-unauthorized", recoverLiffSession);
    return () => {
      window.removeEventListener(
        "strayhub:liff-unauthorized",
        recoverLiffSession,
      );
    };
  }, [pathname, router]);

  if (pathname === "/volunteer-entry") return children;
  if (recoveryPending) return <ProtectedRouteState state="redirecting" />;

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
