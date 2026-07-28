import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";

import "./globals.css";
import AppShell from "@/components/AppShell";
import { AuthProvider } from "@/lib/auth-context";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "AegisAI | Intelligence Platform",
    template: "%s | AegisAI",
  },
  description:
    "AI-powered intelligence platform combining computer vision, threat prediction, GIS visualisation and generative analysis.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: "#05070d",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans text-gray-100 antialiased">
        {/* Decorative only; hidden from assistive tech and under reduced motion. */}
        <div className="glow glow-one" aria-hidden="true" />
        <div className="glow glow-two" aria-hidden="true" />
        <div className="glow glow-three" aria-hidden="true" />

        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
