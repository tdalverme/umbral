"use client";

import { useEffect, useMemo, useState } from "react";

import { RadarSidebar } from "./radar-sidebar";
import { FloatingList } from "./opportunities/floating-list";
import { OpportunityDetailSheet } from "./opportunities/opportunity-detail-sheet";
import { MapLuzSerena } from "./map/map-luz-serena";
import { RadarChatPanel } from "./chat/radar-chat-panel";
import { useRadarSelection } from "@/lib/radar/use-radar-selection";
import type { Explanation, MatchItem, SearchProfile } from "@/lib/radar/client";
import { radarApi } from "@/lib/radar/client";
import type { RadarPoi } from "@/lib/radar/urban";
import { cn } from "@/lib/utils";

export function RadarShell({
  radars,
  selectedRadarId,
  matches,
  explanations,
  opportunitiesFilter,
  header,
  hideSidebar,
}: Readonly<{
  radars: SearchProfile[];
  selectedRadarId: string | null;
  matches: MatchItem[];
  explanations?: Record<string, Explanation>;
  opportunitiesFilter?: "all" | "saved" | "dismissed";
  header?: React.ReactNode;
  hideSidebar?: boolean;
}>) {
  const { selectedId, setSelectedId, filter, setFilter } = useRadarSelection();
  const [collapsed, setCollapsed] = useState(false);
  const [chatCollapsed, setChatCollapsed] = useState(true);
  const [listCollapsed, setListCollapsed] = useState(false);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [mobileView, setMobileView] = useState<"map" | "list" | "chat">("map");
  const [showAll, setShowAll] = useState(false);

  const effectiveFilter = opportunitiesFilter ?? filter;
  const filteredAll = matches.filter((m) => {
    if (effectiveFilter === "all") return true;
    if (effectiveFilter === "saved") return m.decision_state === "save";
    if (effectiveFilter === "dismissed") return m.decision_state === "dismiss";
    return true;
  });
  const filtered = filteredAll.slice(0, 8);
  const visibleOpportunities = showAll ? filtered : filtered.slice(0, 3);

  const selected = filtered.find((m) => m.listing_id === selectedId) ?? null;
  const selectedExplanation = selectedId ? explanations?.[selectedId] : undefined;

  // Qué hay cerca — POIs reales OSM 600m (urban_categories via PostGIS)
  const [visibleCategories, setVisibleCategories] = useState<string[]>([]);
  const [selectedPoiId, setSelectedPoiId] = useState<string | null>(null);
  const [allPois, setAllPois] = useState<RadarPoi[]>([]);

  useEffect(() => {
    if (!selected?.listing_id) {
      setAllPois([]);
      return;
    }
    let cancelled = false;
    radarApi
      .pois(selected.listing_id, 600, 50)
      .then((res) => {
        if (!cancelled) setAllPois(res.pois ?? []);
      })
      .catch(() => {
        if (!cancelled) setAllPois([]);
      });
    return () => {
      cancelled = true;
    };
  }, [selected?.listing_id]);

  const visiblePois = useMemo(
    () => allPois.filter((p) => visibleCategories.includes(p.category)),
    [allPois, visibleCategories],
  );

  useEffect(() => {
    setVisibleCategories([]);
    setSelectedPoiId(null);
  }, [selectedId]);

  const handleToggleCategory = (cat: string) => {
    setVisibleCategories((prev) => (prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]));
    setSelectedPoiId(null);
  };
  const handleToggleAll = () => {
    const cats = [...new Set(allPois.map((p) => p.category))];
    const isAll = cats.length > 0 && cats.every((c) => visibleCategories.includes(c));
    setVisibleCategories(isAll ? [] : cats);
    setSelectedPoiId(null);
  };

  useEffect(() => {
    // MapLibre con trackResize escucha window resize; animación sidebar 320ms → despacha al inicio, mitad y final
    const dispatch = () => window.dispatchEvent(new Event("resize"));
    dispatch();
    const t1 = window.setTimeout(dispatch, 160);
    const t2 = window.setTimeout(dispatch, 340);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [listCollapsed, chatCollapsed, collapsed, selectedId]);

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden bg-background">
      {!hideSidebar && <RadarSidebar radars={radars} selectedId={selectedRadarId} collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />}
      {/* Center: mapa full-bleed + lista flotante colapsable (híbrido B/C) */}
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        {header && <div className="shrink-0 border-b border-border bg-card">{header}</div>}
        <div className="relative flex flex-1 overflow-hidden min-w-0">
          <MapLuzSerena
            matches={filtered}
            selectedId={selectedId}
            hoverId={hoverId}
            onSelect={(id) => {
              setSelectedId(id);
            }}
            pois={visiblePois}
            selectedPoiId={selectedPoiId}
            onPoiSelect={setSelectedPoiId}
          />
          {/* Desktop: lista flotante sobre el mapa, colapsable — z-20 por encima de markers (z 10-12) */}
          <div
            className={cn(
              "absolute bottom-3 top-3 z-20 hidden flex-col motion-safe:transition-[width,opacity,transform] motion-safe:duration-[300ms] motion-safe:ease-[cubic-bezier(0.32,0.08,0.24,1)] lg:flex",
              listCollapsed ? "pointer-events-none w-0 overflow-hidden opacity-0 -translate-x-2" : "left-3 w-[340px] opacity-100 translate-x-0 xl:w-[360px]",
            )}
            aria-hidden={listCollapsed}
          >
            <FloatingList
              opportunities={filtered}
              visibleOpportunities={visibleOpportunities}
              explanations={explanations}
              selectedId={selectedId}
              hoverId={hoverId}
              filter={effectiveFilter}
              onSelect={setSelectedId}
              onHover={setHoverId}
              onFilterChange={setFilter}
              showAll={showAll}
              onToggleShowAll={() => setShowAll((v) => !v)}
              onCollapse={() => setListCollapsed(true)}
            />
          </div>
          {/* Botón flotante para expandir lista cuando está colapsada */}
          {listCollapsed && (
            <button
              aria-label="Mostrar lista de oportunidades"
              className="absolute left-3 top-3 z-20 hidden items-center gap-1.5 rounded-full border border-border bg-card px-3.5 py-2 text-xs font-medium shadow-md hover:bg-muted lg:inline-flex"
              onClick={() => setListCollapsed(false)}
            >
              <span>Lista</span>
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-xs leading-none">{filtered.length}</span>
              <span aria-hidden>»</span>
            </button>
          )}
          {/* Mobile: list overlay when mobileView === list */}
          {mobileView === "list" && (
            <div className="absolute inset-0 z-20 flex flex-col bg-background p-3 lg:hidden">
              <FloatingList
                opportunities={filtered}
                visibleOpportunities={visibleOpportunities}
                explanations={explanations}
                selectedId={selectedId}
                hoverId={hoverId}
                filter={effectiveFilter}
                onSelect={(id) => { setSelectedId(id); setMobileView("map"); }}
                onHover={setHoverId}
                onFilterChange={setFilter}
                showAll={showAll}
                onToggleShowAll={() => setShowAll((v) => !v)}
              />
            </div>
          )}
          {/* Mobile: chat overlay */}
          {mobileView === "chat" && selectedRadarId && (
            <div className="absolute inset-0 z-20 flex flex-col bg-card lg:hidden">
              <div className="flex h-14 items-center justify-between border-b border-border px-4">
                <h2 className="text-sm font-semibold">Conversación</h2>
                <button className="text-xs text-muted-foreground" onClick={() => setMobileView("map")} aria-label="Volver al mapa">Mapa</button>
              </div>
              <div className="flex-1 overflow-hidden">
                <RadarChatPanel profileId={selectedRadarId} />
              </div>
            </div>
          )}
          {/* Desktop: detalle flotante sobre el mapa — z-30 por encima de lista (20) y chat (20) */}
          {selected && (
            <div className="absolute bottom-3 right-3 top-3 z-30 hidden w-[380px] flex-col xl:flex">
              <OpportunityDetailSheet
                opportunity={selected as never}
                explanation={selectedExplanation}
                onClose={() => setSelectedId(null)}
                pois={allPois}
                visibleCategories={visibleCategories}
                onToggleCategory={handleToggleCategory}
                onToggleAll={handleToggleAll}
                selectedPoiId={selectedPoiId}
                onSelectPoi={setSelectedPoiId}
              />
            </div>
          )}
          {/* Mobile: detail sheet as bottom drawer */}
          {selected && mobileView !== "chat" && (
            <div className="absolute inset-x-0 bottom-0 z-20 max-h-[55%] overflow-auto border-t border-border bg-card shadow-lg lg:hidden">
              <OpportunityDetailSheet
                opportunity={selected as never}
                explanation={selectedExplanation}
                onClose={() => setSelectedId(null)}
                pois={allPois}
                visibleCategories={visibleCategories}
                onToggleCategory={handleToggleCategory}
                onToggleAll={handleToggleAll}
                selectedPoiId={selectedPoiId}
                onSelectPoi={setSelectedPoiId}
              />
            </div>
          )}
        </div>
        {/* Mobile tabs — functional, 44px thumb zone */}
        <div className="flex items-center justify-around border-t border-border bg-card p-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] lg:hidden" role="tablist" aria-label="Vistas del radar">
          <button
            role="tab"
            aria-selected={mobileView === "map"}
            aria-label="Ver mapa"
            className={cn("min-h-11 rounded-md px-4 py-2.5 text-sm font-medium", mobileView === "map" ? "bg-muted text-foreground" : "text-muted-foreground")}
            onClick={() => setMobileView("map")}
          >
            Mapa
          </button>
          <button
            role="tab"
            aria-selected={mobileView === "list"}
            aria-label="Ver lista de oportunidades"
            className={cn("min-h-11 rounded-md px-4 py-2.5 text-sm font-medium", mobileView === "list" ? "bg-muted text-foreground" : "text-muted-foreground")}
            onClick={() => setMobileView("list")}
          >
            Lista {filtered.length > 0 ? `(${filtered.length})` : ""}
          </button>
          <button
            role="tab"
            aria-selected={mobileView === "chat"}
            aria-label="Ver chat"
            className={cn("min-h-11 rounded-md px-4 py-2.5 text-sm font-medium", mobileView === "chat" ? "bg-muted text-foreground" : "text-muted-foreground")}
            onClick={() => setMobileView("chat")}
          >
            Chat
          </button>
        </div>
      </div>
      {/* Desktop chat as right aside */}
      <aside
        aria-label="Conversación del radar"
        className={cn(
          "hidden flex-col border-l border-border bg-card motion-safe:transition-[width,opacity] motion-safe:duration-[320ms] motion-safe:ease-[cubic-bezier(0.32,0.08,0.24,1)] xl:flex",
          chatCollapsed ? "w-0 overflow-hidden border-l-0 opacity-0" : "w-[360px] opacity-100 xl:w-[380px]",
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-border px-4">
          <h2 className="text-sm font-semibold">Conversación</h2>
          <button className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted" onClick={() => setChatCollapsed(true)} aria-label="Colapsar chat">
            »
          </button>
        </div>
        <div className="flex-1 overflow-hidden">
          {selectedRadarId ? <RadarChatPanel profileId={selectedRadarId} /> : <p className="p-4 text-sm text-muted-foreground">Seleccioná un radar.</p>}
        </div>
      </aside>
      {chatCollapsed && (
        <button
          className="fixed bottom-4 right-3 z-20 hidden items-center gap-1.5 rounded-full border border-border bg-card px-4 py-2 text-xs font-medium shadow-lg hover:bg-muted xl:inline-flex"
          onClick={() => setChatCollapsed(false)}
          aria-label="Expandir chat"
        >
          <span className="size-2 rounded-full bg-[var(--brand-terracotta)]" aria-hidden />
          Chat <span aria-hidden>«</span>
        </button>
      )}
    </div>
  );
}
