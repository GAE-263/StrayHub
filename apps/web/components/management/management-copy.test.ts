import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const copyContracts = [
  {
    file: "components/management/AppSidebar.tsx",
    removed: [
      /label:\s*"報告收件匣"/,
      /label:\s*"AI Review Queue"/,
      /label:\s*"Audit Query"/,
    ],
    added: [
      /label:\s*"回報收件匣"/,
      /label:\s*"AI 人工覆核"/,
      /label:\s*"稽核紀錄"/,
    ],
  },
  {
    file: "app/management-home.tsx",
    removed: [/開啟\s+Report Inbox/, />\s*AI Review Queue\s*</],
    added: [/開啟回報收件匣/, />\s*AI 人工覆核\s*</],
  },
  {
    file: "app/(management)/ai-review/page.tsx",
    removed: [/AI Review Queue/, /AI Queue/],
    added: [/AI 人工覆核/, /無法載入 AI 人工覆核/, /正在載入 AI 人工覆核/],
  },
  {
    file: "app/(management)/animals/page.tsx",
    removed: [/>\s*Timeline\s*→?\s*</],
    added: [/>\s*近期歷程\s*→?\s*</],
  },
  {
    file: "app/(management)/settings/audit/page.tsx",
    removed: [
      /Audit Query 失敗/,
      /<h1[^>]*>\s*Audit Query\s*<\/h1>/,
      /<label[^>]*>\s*Action\s*<\/label>/,
      /<label[^>]*>\s*Resource type\s*<\/label>/,
    ],
    added: [
      /稽核紀錄查詢失敗/,
      /<h1[^>]*>\s*稽核紀錄查詢\s*<\/h1>/,
      /<label[^>]*>\s*動作（Action）\s*<\/label>/,
      /<label[^>]*>\s*資源類型（Resource type）\s*<\/label>/,
    ],
  },
  {
    file: "features/report-inbox/ReportInbox.tsx",
    removed: [
      /Report Inbox 載入失敗/,
      /無法載入 Report Inbox/,
      /查看 Detail/,
      /回報 Detail 載入失敗/,
      /無法載入回報 Detail/,
      /正在載入回報 Detail/,
      />\s*保存 Correction\s*</,
      />\s*Archive\s*</,
      />\s*回到 Timeline\s*</,
    ],
    added: [
      /照護回報收件匣/,
      /正在載入回報/,
      /查看完整志工回報/,
      /回報詳情/,
      /保存更正/,
      /封存回報/,
      /查看動物近期歷程/,
    ],
  },
  {
    file: "app/(management)/animals/[animalId]/page.tsx",
    removed: [/<strong>\s*Timeline\s*<\/strong>/],
    added: [/<strong>\s*近期歷程\s*<\/strong>/],
  },
  {
    file: "app/login/LoginClient.tsx",
    removed: [/Active Shelter Context/, /Membership/],
    added: [/目前收容所/, /登入設定/],
  },
  {
    file: "components/management/ManagementLayout.tsx",
    removed: [
      /Active Shelter Context/,
      /管理工作台 Context/,
      /Context 切換失敗/,
      /重新驗證 Session 與 Membership/,
    ],
    added: [/目前收容所/, /管理工作台權限/, /登入狀態/, /成員資格/],
  },
  {
    file: "app/(management)/shelters/page.tsx",
    removed: [/帳號與 Membership 已建立/],
    added: [/帳號與成員資格已建立/],
  },
  {
    file: "app/(management)/shelters/archived/page.tsx",
    removed: [/帳號與 Membership/, /恢復 Membership/],
    added: [/帳號與成員資格/, /恢復成員資格/],
  },
] as const;

describe("management interface copy", () => {
  it("uses Traditional Chinese for navigation, titles, actions, and fields", () => {
    for (const contract of copyContracts) {
      const source = readFileSync(join(process.cwd(), contract.file), "utf8");
      for (const oldCopy of contract.removed) {
        expect(source, `${contract.file}: ${oldCopy}`).not.toMatch(oldCopy);
      }
      for (const localizedCopy of contract.added) {
        expect(source, `${contract.file}: ${localizedCopy}`).toMatch(
          localizedCopy,
        );
      }
    }
  });
});
