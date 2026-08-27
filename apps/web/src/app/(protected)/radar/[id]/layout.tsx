import type { ReactNode } from "react";

export default function RadarIdLayout({ children }: Readonly<{ children: ReactNode }>) {
  // Shell landmarks are provided by RadarShell; this layout preserves protected context and providers
  return <>{children}</>;
}
