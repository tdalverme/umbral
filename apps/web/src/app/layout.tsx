import type { Metadata } from "next";
import type { ReactNode } from "react";

import { GlobalAttribution } from "@/components/global-attribution";
import "./globals.css";

export const metadata: Metadata = {
  title: "Umbral",
  description: "Fundación del runtime de Umbral",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="es-AR">
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
