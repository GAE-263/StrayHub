import { beforeEach, describe, expect, it, vi } from "vitest";
import liff from "@line/liff";
import {
  CARE_REPORT_TRIGGER_TEXT,
  attemptCareReportLineTrigger,
  closeLiffWindow,
} from "./liff-line-handoff";

vi.mock("@line/liff", () => ({
  default: {
    id: "test-liff-id",
    isInClient: vi.fn(),
    permission: { query: vi.fn() },
    sendMessages: vi.fn(),
    closeWindow: vi.fn(),
  },
}));

const mockedLiff = vi.mocked(liff);
const permissionQuery = vi.mocked(liff.permission.query);

beforeEach(() => {
  Object.defineProperty(mockedLiff, "id", {
    configurable: true,
    value: "test-liff-id",
  });
  mockedLiff.isInClient.mockReset().mockReturnValue(true);
  permissionQuery.mockReset().mockResolvedValue({
    state: "granted",
  });
  mockedLiff.sendMessages.mockReset().mockResolvedValue();
  mockedLiff.closeWindow.mockReset();
});

describe("LIFF care-report trigger", () => {
  it("sends only the fixed trigger text when initialized, in client, and permitted", async () => {
    await expect(attemptCareReportLineTrigger()).resolves.toEqual({
      status: "sent",
      canClose: true,
    });
    expect(mockedLiff.sendMessages).toHaveBeenCalledOnce();
    expect(mockedLiff.sendMessages).toHaveBeenCalledWith([
      { type: "text", text: CARE_REPORT_TRIGGER_TEXT },
    ]);
    expect(JSON.stringify(mockedLiff.sendMessages.mock.calls)).not.toMatch(
      /animal_id|handoff_id|confirmation_token|membership_id/,
    );
  });

  it.each([
    ["not initialized", null, true, "granted"],
    ["external browser", "test-liff-id", false, "granted"],
    ["permission unavailable", "test-liff-id", true, "unavailable"],
  ])("reports unavailable when %s", async (_label, id, inClient, state) => {
    Object.defineProperty(mockedLiff, "id", {
      configurable: true,
      value: id,
    });
    mockedLiff.isInClient.mockReturnValue(inClient as boolean);
    permissionQuery.mockResolvedValue({ state } as never);

    await expect(attemptCareReportLineTrigger()).resolves.toEqual({
      status: "unavailable",
      canClose: id !== null && inClient,
    });
    expect(mockedLiff.sendMessages).not.toHaveBeenCalled();
  });

  it("keeps a usable fallback when sendMessages rejects", async () => {
    mockedLiff.sendMessages.mockRejectedValue(new Error("denied"));
    await expect(attemptCareReportLineTrigger()).resolves.toEqual({
      status: "failed",
      canClose: true,
    });
  });

  it("closes only in an initialized in-client runtime and handles failure", () => {
    expect(closeLiffWindow()).toBe(true);
    expect(mockedLiff.closeWindow).toHaveBeenCalledOnce();

    mockedLiff.closeWindow.mockImplementation(() => {
      throw new Error("not closable");
    });
    expect(closeLiffWindow()).toBe(false);

    mockedLiff.isInClient.mockReturnValue(false);
    expect(closeLiffWindow()).toBe(false);
  });
});
