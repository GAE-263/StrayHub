"use client";

import React, { type ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft, PawPrint } from "lucide-react";
import styles from "./identity.module.css";

export function IdentityShell({
  children,
  title,
  description,
  eyebrow,
  actions,
  back,
  login = false,
}: {
  children: ReactNode;
  title: string;
  description?: string;
  eyebrow?: string;
  actions?: ReactNode;
  back?: { href: string; label: string };
  login?: boolean;
}) {
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <Link
          href={login ? "/login" : "/access"}
          className={styles.brand}
          aria-label="浪浪森友會"
        >
          <span className={styles.mark}>森</span>
          <span>
            <strong>浪浪森友會</strong>
            <small>STRAYHUB · 一起照顧牠的日常</small>
          </span>
        </Link>
        <nav aria-label="使用者導覽" className={styles.actions}>
          {actions}
        </nav>
      </header>
      <main
        id="identity-main"
        className={login ? styles.loginLayout : styles.main}
      >
        {login && (
          <aside className={styles.story} aria-label="一起照顧浪浪">
            <span className={styles.storyLabel}>
              <PawPrint size={18} aria-hidden="true" /> 每一份照顧，都有你的位置
            </span>
            <h2>
              把時間留給
              <br />
              需要你的牠。
            </h2>
            <p>
              從日常照護到找到一個家，
              <br />
              讓每一份用心，都好好接續。
            </p>
            <span className={styles.forest} aria-hidden="true">
              森
            </span>
            <div className={styles.storyFoot}>
              <span>浪浪森友會</span>
              <span>照顧，一起完成。</span>
            </div>
          </aside>
        )}
        <div className={login ? styles.loginBody : undefined}>
          {back && (
            <Link href={back.href} className={styles.back}>
              <ArrowLeft size={16} aria-hidden="true" />
              {back.label}
            </Link>
          )}
          <div className={styles.pageHeading}>
            {eyebrow && <span className={styles.eyebrow}>{eyebrow}</span>}
            <h1>{title}</h1>
            {description && <p>{description}</p>}
          </div>
          {children}
        </div>
      </main>
      <footer className={styles.footer}>
        浪浪森友會 <span aria-hidden="true">·</span> 讓照顧，成為牠安心的日常。
      </footer>
    </div>
  );
}

export function IdentityNotice({
  children,
  error = false,
}: {
  children: ReactNode;
  error?: boolean;
}) {
  return (
    <div
      className={`${styles.notice} ${error ? styles.noticeError : ""}`}
      role={error ? "alert" : "status"}
    >
      {children}
    </div>
  );
}
