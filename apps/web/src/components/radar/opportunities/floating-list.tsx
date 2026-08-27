"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { MatchItem } from "@/lib/radar/client";

export function FloatingList({
  opportunities,
  selectedId,
  hoverId,
  filter,
  onSelect,
  onHover,
  onFilterChange,
}: Readonly<{
  opportunities: MatchItem[];
  selectedId: string | null;
  hoverId: string | null;
  filter: "all" | "saved" | "dismissed";
  onSelect: (id: string | null) => void;
  onHover: (id: string | null) => void;
  onFilterChange?: (f: "all" | "saved" | "dismissed") => void;
}>) {
  const tabs: Array<{ v: typeof filter; label: string }> = [
    { v: "all", label: "Todos" },
    { v: "saved", label: "Guardadas" },
    { v: "dismissed", label: "Descartadas" },
  ];
  return (
    <div className="flex h-full flex-col rounded-xl border border-border bg-card shadow-sm">
      <div className="flex items-center justify-between border-b border-border p-3">
        <h2 className="text-sm font-semibold">{opportunities.length} oportunidades</h2>
        <span className="text-xs text-muted-foreground">curadas</span>
      </div>
      <div className="flex gap-1 border-b border-border p-2">
        {tabs.map((t) => (
          <Button
            key={t.v}
            className={cn("h-7 px-2 text-xs", filter === t.v ? "" : "bg-muted text-foreground hover:bg-muted/80")}
            onClick={() => onFilterChange?.(t.v)}
          >
            {t.label}
          </Button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto p-2" role="list" aria-label="Lista de oportunidades">
        {opportunities.length === 0 ? (
          <Card>
            <CardContent className="py-6 text-sm text-muted-foreground">No hay oportunidades que cumplan tu radar. Probá ajustar el radar en el chat.</CardContent>
          </Card>
        ) : (
          <ul className="space-y-2">
            {opportunities.map((o) => (
              <li key={o.listing_id} role="listitem">
                <button
                  className={cn(
                    "w-full rounded-lg border p-3 text-left hover:border-ring focus-visible:ring-2 focus-visible:ring-ring",
                    selectedId === o.listing_id && "border-ring ring-1 ring-ring",
                    hoverId === o.listing_id && "bg-muted/50",
                  )}
                  aria-selected={selectedId === o.listing_id}
                  onClick={() => onSelect(o.listing_id)}
                  onMouseEnter={() => onHover(o.listing_id)}
                  onMouseLeave={() => onHover(null)}
                  onFocus={() => onHover(o.listing_id)}
                  onBlur={() => onHover(null)}
                >
                  <p className="text-sm font-medium">{o.neighborhood ?? "Barrio no declarado"} · ${Number(o.total_cost ?? 0).toLocaleString("es-AR")}</p>
                  <p className="text-xs text-muted-foreground">
                    {o.surface_m2 ?? "—"} m² · {o.rooms ?? "—"} amb · {o.source_id ?? "—"}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">Por qué encaja: cercanía a lo que pediste.</p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {opportunities.length === 8 && <p className="p-2 text-center text-xs text-muted-foreground">Mostrando 8 curadas.</p>}
    </div>
  );
}
