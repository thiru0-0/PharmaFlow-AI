import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "PharmaFlow AI — Reverse Chain Compliance",
  description: "CDSCO drug disposal reverse-chain coordination, audit and re-entry fraud detection.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
