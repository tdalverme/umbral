import type { Metadata } from "next";
import type { ReactNode } from "react";
import { DM_Sans, Fraunces } from "next/font/google";

import { GlobalAttribution } from "@/components/global-attribution";
import "./globals.css";

const dmSans = DM_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-brand",
});

export const metadata: Metadata = {
  title: "Umbral",
  description: "Fundación del runtime de Umbral",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="es-AR" className={`${dmSans.variable} ${fraunces.variable}`}>
      <body>
        <a className="skip-link" href="#main-content">
          Saltar al contenido principal
        </a>
        <div id="main-content">{children}</div>
        <GlobalAttribution />
      </body>
    </html>
  );
}
