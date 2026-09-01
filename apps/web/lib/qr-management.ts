import type { components } from "../../../packages/contracts/src/openapi";

export type ManagementQrCodeList =
  components["schemas"]["ManagementQrCodeList"];
export type ManagementQrCodeListItem =
  components["schemas"]["ManagementQrCodeListItem"];

const qrCreatedAtFormatter = new Intl.DateTimeFormat("zh-TW", {
  timeZone: "Asia/Taipei",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export function formatQrCreatedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "時間未提供";
  const parts = Object.fromEntries(
    qrCreatedAtFormatter
      .formatToParts(date)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value]),
  );
  return `${parts.year}/${parts.month}/${parts.day} ${parts.hour}:${parts.minute}`;
}

export function isActiveQr(item: ManagementQrCodeListItem) {
  return item.status === "active" && !item.revoked;
}

export function qrStatusLabel(item: ManagementQrCodeListItem) {
  return isActiveQr(item) ? "使用中" : "已撤銷";
}
