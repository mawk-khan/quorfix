import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bug Fixer",
  description: "Bug Fixer — open-core bug tracking",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
