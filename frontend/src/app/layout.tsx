import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/app-shell";

import { Providers } from "./providers";

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
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
