"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { snapshotBadge } from "@/lib/urban/signal-meta";
import { neighborhoodLabel } from "@/lib/radar/neighborhoods";
import type { Explanation } from "@/lib/radar/client";
import type { RadarPoi, PoiCategory } from "@/lib/radar/urban";
import { POI_CATEGORY_META } from "@/lib/radar/urban";
import { cn } from "@/lib/utils";

export function OpportunityDetailSheet({
  opportunity,
  explanation,
  onClose,
  pois = [],
  visibleCategories = [],
  onToggleCategory,
  onToggleAll,
  selectedPoiId = null,
  onSelectPoi,
}: Readonly<{
  opportunity: { listing_id: string; neighborhood: string | null; total_cost: number | null; surface_m2: number | null; rooms: number | null; url?: string | null };
  explanation?: Explanation;
  onClose: () => void;
  pois?: RadarPoi[];
  visibleCategories?: string[];
  onToggleCategory?: (category: string) => void;
  onToggleAll?: () => void;
  selectedPoiId?: string | null;
  onSelectPoi?: (id: string | null) => void;
}>) {
  const ref = useRef<HTMLHeadingElement>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [showAllPois, setShowAllPois] = useState(false);
  const [entornoOpen, setEntornoOpen] = useState(false);
  const [reparosOpen, setReparosOpen] = useState(false);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  useEffect(() => {
    setFeedback(null);
    setShowAllPois(false);
    setEntornoOpen(false);
    // abrir reparos solo si hay algo que realmente frene
    const hasReparos = Boolean(
      explanation && (explanation.risks.length > 0 || explanation.missing_data.length > 0),
    );
    setReparosOpen(hasReparos && (explanation?.risks.length ?? 0) > 0);
  }, [opportunity.listing_id, explanation]);

  const handleSave = () => setFeedback("Guardada — queda arriba en tu radar. Podés deshacer.");
  const handleDismiss = () => setFeedback("Descartada — no la verás más. Si es por un filtro definitivo, te pido confirmar.");

  const uniqueCategories = [...new Set(pois.map((p) => p.category))].sort((a, b) => a.localeCompare(b));
  const isAllVisible = uniqueCategories.length > 0 && uniqueCategories.every((c) => visibleCategories.includes(c));
  const filteredPois = pois.filter((p) => visibleCategories.includes(p.category)).sort((a, b) => a.distance_m - b.distance_m);
  const visibleList = showAllPois ? filteredPois : filteredPois.slice(0, 3);
  const hasPois = pois.length > 0;
  const hasReparos = Boolean(explanation && (explanation.risks.length > 0 || explanation.missing_data.length > 0));

  // Señales urbanas compactas — una línea, no dos
  const snapshot = snapshotBadge({ date: "2026-08-20", sha256: "abc123def456" });

  return (
    <Card className="flex h-full flex-col overflow-hidden rounded-xl border-border bg-card shadow-lg">
      {/* Header — denso arriba, aire abajo */}
      <CardHeader className="shrink-0 border-b border-border bg-card px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <h2 ref={ref} tabIndex={-1} className="max-w-[22ch] text-lg font-semibold leading-tight tracking-[-0.02em] text-foreground outline-none">
            {opportunity.neighborhood ? neighborhoodLabel(opportunity.neighborhood) : "Oportunidad"}
          </h2>
          <button
            type="button"
            aria-label="Cerrar detalle"
            onClick={onClose}
            className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span aria-hidden className="text-lg leading-none">×</span>
          </button>
        </div>
        <p className="mt-1.5 flex flex-wrap items-center gap-2 text-sm">
          <span className="font-semibold text-foreground">${Number(opportunity.total_cost ?? 0).toLocaleString("es-AR")}</span>
          <span className="text-muted-foreground">·</span>
          <span className="text-muted-foreground">
            {opportunity.surface_m2 != null ? `${opportunity.surface_m2} m²` : "sup. no declarada"} · {opportunity.rooms != null ? `${opportunity.rooms} amb.` : "amb. no declarados"}
          </span>
        </p>
      </CardHeader>

      <CardContent className="flex-1 overflow-y-auto px-5 py-5">
        {/* Ritmo: grupos separados 24px, dentro 10-12px */}
        <div className="space-y-6">
          {/* 1 — Por qué encaja: primario, con aire */}
          <section className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-foreground">Por qué encaja</h3>
            {explanation?.reasons?.length ? (
              <ul className="space-y-2.5">
                {explanation.reasons.slice(0, 2).map((r) => (
                  <li key={r.criterion_key} className="flex gap-2.5">
                    <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-emerald-500" aria-hidden />
                    <p className="text-sm leading-relaxed text-foreground">
                      {r.text}
                      <span className="text-xs text-muted-foreground"> — {r.evidence_level === "strong" ? "evidencia clara" : r.evidence_level === "medium" ? "evidencia media" : "a confirmar"}</span>
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm leading-relaxed text-muted-foreground">Tu radar lo evaluará en el próximo barrido. Te avisa solo si realmente encaja.</p>
            )}
            {explanation?.reasons?.length && explanation.reasons.length > 2 && (
              <p className="text-xs text-muted-foreground">+{explanation.reasons.length - 2} coincidencia más · se priorizan las que más pesan para vos.</p>
            )}
          </section>

          {/* 2 — A tener en cuenta: disclosure, no bloque fijo */}
          {hasReparos && (
            <section className="rounded-xl border border-border bg-muted/20">
              <button
                type="button"
                aria-expanded={reparosOpen}
                onClick={() => setReparosOpen((v) => !v)}
                className="flex w-full items-center justify-between gap-2 px-3.5 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset rounded-xl"
              >
                <span className="text-xs font-semibold uppercase tracking-wide text-foreground">Antes de decidir</span>
                <span className="flex items-center gap-2">
                  <span className="hidden text-xs text-muted-foreground sm:inline">
                    {explanation?.risks.length ? `${explanation.risks.length} punto${explanation.risks.length > 1 ? "s" : ""}` : ""} {explanation?.missing_data.length ? `· falta ${explanation.missing_data[0]}` : ""}
                  </span>
                  <span className={cn("text-muted-foreground transition-transform duration-200", reparosOpen && "rotate-180")} aria-hidden>
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M4 6l4 4 4-4" /></svg>
                  </span>
                </span>
              </button>
              {reparosOpen && (
                <div className="space-y-2 border-t border-border/60 px-3.5 py-3">
                  {explanation?.risks.slice(0, 2).map((rk) => (
                    <p key={rk.criterion_key} className="text-sm leading-relaxed text-muted-foreground">· {rk.text}</p>
                  ))}
                  {explanation?.missing_data?.length ? (
                    <p className="text-sm leading-relaxed text-muted-foreground">
                      Falta confirmar: <span className="font-medium text-foreground">{explanation.missing_data.slice(0, 2).join(", ")}</span> — lo preguntamos en la visita.
                    </p>
                  ) : null}
                </div>
              )}
            </section>
          )}

          {/* Acciones — jerarquía clara: 1 primaria, 2 secundarias */}
          <div className="flex flex-wrap gap-2 pt-1">
            {opportunity.url ? (
              <a
                href={opportunity.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 items-center justify-center rounded-md bg-foreground px-3.5 text-xs font-medium text-card shadow-xs transition-colors hover:bg-foreground/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Ver aviso
              </a>
            ) : (
              <Button className="h-8 bg-foreground px-3.5 text-xs text-card hover:bg-foreground/90" onClick={() => window.open(`/listings/${opportunity.listing_id}`, "_blank")}>Ver aviso</Button>
            )}
            <button
              type="button"
              onClick={handleSave}
              className="inline-flex h-8 items-center justify-center rounded-md border border-border bg-card px-3.5 text-xs font-medium text-foreground shadow-xs hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Guardar
            </button>
            <button
              type="button"
              onClick={handleDismiss}
              className="inline-flex h-8 items-center justify-center rounded-md px-3 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Descartar
            </button>
          </div>

          {feedback && (
            <div role="status" className="rounded-lg border border-border bg-muted/40 px-3 py-2.5 text-sm leading-relaxed text-foreground">
              {feedback}
            </div>
          )}

          {/* Separador — aire antes de lo secundario */}
          <div className="border-t border-border pt-6">
            {/* 3 — Qué hay cerca: único bloque de entorno, sin duplicar */}
            <section className="space-y-3">
              <button
                type="button"
                aria-expanded={entornoOpen}
                onClick={() => setEntornoOpen((v) => !v)}
                className="flex w-full items-center justify-between gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md -mx-1 px-1 py-1"
              >
                <span className="text-xs font-semibold uppercase tracking-wide text-foreground">Qué hay cerca</span>
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="hidden sm:inline">A 600 m · {hasPois ? `${pois.length} lugares · OSM` : "OSM"}</span>
                  <span className={cn("transition-transform duration-200", entornoOpen && "rotate-180")} aria-hidden>
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M4 6l4 4 4-4" /></svg>
                  </span>
                </span>
              </button>

              {entornoOpen && (
                <div className="space-y-3 border-t border-border/60 pt-4 motion-safe:animate-in">

                  {!hasPois ? (
                    <p className="text-sm leading-relaxed text-muted-foreground">Elegí otra oportunidad con ubicación para ver comercios, escuelas y transporte cercanos.</p>
                  ) : (
                    <>
                      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filtrar categorías en el mapa">
                        <button
                          type="button"
                          aria-pressed={isAllVisible}
                          onClick={() => onToggleAll?.()}
                          className={cn(
                            "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                            isAllVisible
                              ? "border-foreground bg-foreground text-card shadow-xs"
                              : "border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground",
                          )}
                        >
                          Todos <span className="ml-1 text-xs opacity-70">{pois.length}</span>
                        </button>
                        {uniqueCategories.slice(0, 6).map((cat) => {
                          const meta = POI_CATEGORY_META[cat as PoiCategory] ?? { label: cat, color: "#4A6B5E" };
                          const active = visibleCategories.includes(cat);
                          const count = pois.filter((p) => p.category === cat).length;
                          return (
                            <button
                              key={cat}
                              type="button"
                              aria-pressed={active}
                              onClick={() => onToggleCategory?.(cat)}
                              className={cn(
                                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                                active
                                  ? "border-foreground bg-foreground text-card shadow-xs"
                                  : "border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground",
                              )}
                            >
                              <span className="size-1.5 rounded-full" style={{ backgroundColor: meta.color }} aria-hidden />
                              {meta.label} <span className="text-xs opacity-70">{count}</span>
                            </button>
                          );
                        })}
                        {uniqueCategories.length > 6 && (
                          <span className="inline-flex items-center px-1 text-xs text-muted-foreground">+{uniqueCategories.length - 6}</span>
                        )}
                      </div>

                      {visibleCategories.length === 0 ? (
                        <p className="rounded-lg border border-dashed border-border bg-muted/30 px-3 py-3 text-center text-sm leading-relaxed text-muted-foreground">
                          Tocá una categoría para pintarla en el mapa.
                        </p>
                      ) : filteredPois.length === 0 ? (
                        <p className="text-sm text-muted-foreground">Nada de eso a 600 m.</p>
                      ) : (
                        <>
                          <ul className="space-y-1.5" role="list" aria-label="POIs cercanos">
                            {visibleList.map((poi) => {
                              const meta = POI_CATEGORY_META[poi.category as PoiCategory] ?? { label: poi.category, color: "#4A6B5E" };
                              const isSelected = poi.id === selectedPoiId;
                              return (
                                <li key={poi.id}>
                                  <button
                                    type="button"
                                    onClick={() => onSelectPoi?.(isSelected ? null : poi.id)}
                                    aria-pressed={isSelected}
                                    className={cn(
                                      "flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                                      isSelected ? "border-foreground bg-muted" : "border-border bg-card hover:bg-muted/50",
                                    )}
                                  >
                                    <span className="size-2 rounded-full shrink-0" style={{ backgroundColor: meta.color }} aria-hidden />
                                    <span className="min-w-0 flex-1 truncate text-sm font-medium leading-tight text-foreground">{poi.name}</span>
                                    <span className="shrink-0 text-xs tabular-nums text-muted-foreground">a {poi.distance_m} m</span>
                                  </button>
                                </li>
                              );
                            })}
                          </ul>
                          {filteredPois.length > 3 && (
                            <button
                              type="button"
                              onClick={() => setShowAllPois((v) => !v)}
                              className="text-xs font-medium text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground"
                            >
                              {showAllPois ? "Ver menos" : `Ver ${filteredPois.length - 3} más`}
                            </button>
                          )}
                        </>
                      )}
                    </>
                  )}
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    {snapshot} · Distancias en línea recta · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer" className="underline decoration-border underline-offset-4 hover:text-foreground">© OpenStreetMap</a> · contrato v2
                  </p>
                </div>
              )}
            </section>
          </div>

          <p className="border-t border-border pt-4 text-xs leading-relaxed text-muted-foreground">Tu radar decide — vos confirmás. Lo suave reordena, lo definitivo solo con tu OK y se puede deshacer.</p>
        </div>
      </CardContent>
    </Card>
  );
}
