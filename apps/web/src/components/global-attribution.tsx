import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export const OSM_ATTRIBUTION = "© OpenStreetMap contributors";

interface GlobalAttributionProps extends HTMLAttributes<HTMLElement> {
  href?: string;
}

export function GlobalAttribution({
  className,
  href = "https://www.openstreetmap.org/copyright",
  ...props
}: GlobalAttributionProps) {
  return (
    <footer
      data-slot="global-attribution"
      className={cn(
        "border-t px-6 py-3 text-xs text-muted-foreground",
        className,
      )}
      {...props}
    >
      <a href={href} target="_blank" rel="noreferrer" className="hover:underline">
        {OSM_ATTRIBUTION}
      </a>
    </footer>
  );
}
