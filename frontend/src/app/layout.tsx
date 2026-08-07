import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/app-shell";
import { PRODUCT_NAME, PRODUCT_TAGLINE } from "@/lib/branding";

import { Providers } from "./providers";

// Self-hosted at build time (next/font downloads once during `next build`
// and serves the files from this app's own origin under /_next/static) —
// never a runtime request to fonts.googleapis.com, so the existing
// `font-src 'self'` CSP directive (next.config.ts) already covers this
// without any change. No font binaries are committed: next/font's download
// cache lives under .next/, which is gitignored.
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: PRODUCT_NAME,
  description: `${PRODUCT_NAME} — ${PRODUCT_TAGLINE}`,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans antialiased">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
