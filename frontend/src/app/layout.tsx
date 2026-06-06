import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "A Trading System",
  description: "Personal A-share trading system management platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
