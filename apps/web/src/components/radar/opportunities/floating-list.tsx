"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Explanation, MatchItem } from "@/lib/radar/client";
import { neighborhoodLabel } from "@/lib/radar/neighborhoods";

function formatScore(score: number | null | undefined): string {
  if (score == null || typeof score !== "number" || Number.isNaN(score)) return "—";
  return new Intl.NumberFormat("es-AR", {
    style: "percent",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(score);
}

function EvidenceDot({ level }: { level: "strong" | "medium" | "low" }) {
  const map: Record<string, string> = {
    strong: "bg-emerald-500",
    medium: "bg-amber-500",
    low: "bg-muted-foreground/40",
  };
  return <span className={cn("size-1 shrink-0 rounded-full mt-[6px]", map[level])} aria-hidden="true" />;
}

export function FloatingList({
  opportunities,
  visibleOpportunities,
  explanations,
  selectedId,
  hoverId,
  filter,
  onSelect,
  onHover,
  onFilterChange,
  showAll,
  onToggleShowAll,
  onCollapse,
}: Readonly<{
  opportunities: MatchItem[];
  visibleOpportunities?: MatchItem[];
  explanations?: Record<string, Explanation>;
  selectedId: string | null;
  hoverId: string | null;
  filter: "all" | "saved" | "dismissed";
  onSelect: (id: string | null) => void;
  onHover: (id: string | null) => void;
  onFilterChange?: (f: "all" | "saved" | "dismissed") => void;
  showAll?: boolean;
  onToggleShowAll?: () => void;
  onCollapse?: () => void;
}>) {
  const tabs: Array<{ v: typeof filter; label: string }> = [
    { v: "all", label: "Todos" },
    { v: "saved", label: "Guardadas" },
    { v: "dismissed", label: "Descartadas" },
  ];
  const displayList = visibleOpportunities ?? opportunities;
  const hasMore = opportunities.length > displayList.length;

  return (
    <div className="flex h-full flex-col rounded-xl border border-border bg-card shadow-lg">
      <div className="flex items-center justify-between border-b border-border p-3">
        <h2 className="text-sm font-semibold">{opportunities.length} oportunidades</h2>
        <span className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground" title="Selección breve explicada por tu radar, no ranking opaco">curadas</span>
          {onCollapse && (
            <button
              aria-label="Ocultar lista"
              className="rounded-md p-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={onCollapse}
            >
              «
            </button>
          )}
        </span>
      </div>
      <div className="flex gap-1 border-b border-border p-2">
        {tabs.map((t) => (
          <Button
            key={t.v}
            aria-pressed={filter === t.v}
            className={cn("min-h-9 px-3 py-2 text-xs", filter === t.v ? "" : "bg-muted text-foreground hover:bg-muted/80")}
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
            {displayList.map((o) => {
              const exp = explanations?.[o.listing_id];
              const topReason = exp?.reasons?.[0];
              const secondReason = exp?.reasons?.[1];
              const risk = exp?.risks?.[0];
              const missing = exp?.missing_data?.[0];
              const isSelected = selectedId === o.listing_id;
              return (
                <li key={o.listing_id} role="listitem">
                  <button
                    className={cn(
                      "relative w-full rounded-lg border bg-card p-3 text-left transition-colors hover:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      isSelected && "border-ring ring-1 ring-ring",
                      hoverId === o.listing_id && "bg-muted/50",
                    )}
                    aria-selected={isSelected}
                    onClick={() => onSelect(o.listing_id)}
                    onMouseEnter={() => onHover(o.listing_id)}
                    onMouseLeave={() => onHover(null)}
                    onFocus={() => onHover(o.listing_id)}
                    onBlur={() => onHover(null)}
                  >
                    <span className="flex items-start justify-between gap-2">
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span
                            className={cn("size-2 shrink-0 rounded-full border border-border", isSelected ? "bg-[var(--brand-terracotta)] border-[var(--brand-terracotta)]" : "bg-[var(--brand-forest)]")}
                            aria-hidden="true"
                          />
                          <span className="truncate text-sm font-medium leading-none">
                            {o.neighborhood ? neighborhoodLabel(o.neighborhood) : "Barrio no declarado"} · ${Number(o.total_cost ?? 0).toLocaleString("es-AR")}
                          </span>
                        </span>
                        <span className="mt-0.5 block text-xs text-muted-foreground">
                          {o.surface_m2 != null ? `${o.surface_m2} m²` : "superficie no declarada"} · {o.rooms != null ? `${o.rooms} amb` : "ambientes no declarados"}
                        </span>
                      </span>
                      <span className="shrink-0 text-xs font-medium tabular-nums text-muted-foreground">{formatScore(o.score)}</span>
                    </span>
                    {exp ? (
                      <span className="mt-2 block space-y-1">
                        {topReason ? (
                          <span className="flex items-start gap-1.5 text-xs">
                            <EvidenceDot level={topReason.evidence_level} />
                            <span className="leading-4">{topReason.text}</span>
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">Aún sin análisis detallado — se actualizará en el próximo run.</span>
                        )}
                        {secondReason && (
                          <span className="flex items-start gap-1.5 text-xs text-muted-foreground">
                            <EvidenceDot level={secondReason.evidence_level} />
                            <span className="leading-4">{secondReason.text}</span>
                          </span>
                        )}
                        {(risk || missing) && (
                          <span className="block text-xs text-muted-foreground">
                            {risk ? `Concesión: ${risk.text}` : `No sabemos: ${missing}`}
                          </span>
                        )}
                      </span>
                    ) : (
                      <span className="mt-1 block text-xs text-muted-foreground">Por qué encaja: se generará con el próximo run del radar.</span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {hasMore && onToggleShowAll && (
        <div className="border-t border-border p-2">
          <Button className="min-h-9 w-full bg-muted px-3 py-2 text-xs text-foreground hover:bg-muted/80" onClick={onToggleShowAll}>
            {showAll ? "Ver menos" : `Ver ${opportunities.length - displayList.length} más`}
          </Button>
        </div>
      )}
      {opportunities.length === 8 && !hasMore && <p className="p-2 text-center text-xs text-muted-foreground">Mostrando 8 curadas — ajustá el radar para más o menos.</p>}
    </div>
  );
}
