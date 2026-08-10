import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "浪浪森友會",
  description: "志工日常照護回報與動物近期歷程",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant-TW">
      <body>{children}</body>
    </html>
  );
}
