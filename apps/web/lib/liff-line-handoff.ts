import liff from "@line/liff";

export const CARE_REPORT_TRIGGER_TEXT = "開始散步回報";

export type LineTriggerResult = {
  status: "sent" | "unavailable" | "failed";
  canClose: boolean;
};

function isInitializedInClient(): boolean {
  try {
    return liff.id !== null && liff.isInClient();
  } catch {
    return false;
  }
}

function canCloseLiffWindow(): boolean {
  return isInitializedInClient() && typeof liff.closeWindow === "function";
}

export async function attemptCareReportLineTrigger(): Promise<LineTriggerResult> {
  const canClose = canCloseLiffWindow();
  if (!isInitializedInClient() || typeof liff.sendMessages !== "function") {
    return { status: "unavailable", canClose };
  }

  try {
    const permission = await liff.permission.query("chat_message.write");
    if (permission.state === "unavailable") {
      return { status: "unavailable", canClose };
    }
    await liff.sendMessages([{ type: "text", text: CARE_REPORT_TRIGGER_TEXT }]);
    return { status: "sent", canClose };
  } catch {
    return { status: "failed", canClose };
  }
}

export function closeLiffWindow(): boolean {
  if (!canCloseLiffWindow()) return false;
  try {
    liff.closeWindow();
    return true;
  } catch {
    return false;
  }
}
