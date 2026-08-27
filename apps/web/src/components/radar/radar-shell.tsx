"use client";

import { useState } from "react";

import { RadarSidebar } from "./radar-sidebar";
import { FloatingList } from "./opportunities/floating-list";
import { OpportunityDetailSheet } from "./opportunities/opportunity-detail-sheet";
import { MapLuzSerena } from "./map/map-luz-serena";
import { RadarChatPanel } from "./chat/radar-chat-panel";
import { useRadarSelection } from "@/lib/radar/use-radar-selection";
import type { MatchItem, SearchProfile } from "@/lib/radar/client";
import { cn } from "@/lib/utils";

export function RadarShell({
  radars,
  selectedRadarId,
  matches,
  opportunitiesFilter,
}: Readonly<{
  radars: SearchProfile[];
  selectedRadarId: string | null;
  matches: MatchItem[];
  opportunitiesFilter?: "all" | "saved" | "dismissed";
}>) {
  const { selectedId, setSelectedId, filter, setFilter } = useRadarSelection();
  const [collapsed, setCollapsed] = useState(false);
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const [hoverId, setHoverId] = useState<string | null>(null);

  const effectiveFilter = opportunitiesFilter ?? filter;
  const filtered = matches.slice(0, 8).filter((m) => {
    if (effectiveFilter === "all") return true;
    if (effectiveFilter === "saved") return m.decision_state === "save";
    if (effectiveFilter === "dismissed") return m.decision_state === "dismiss";
    return true;
  });

  const selected = filtered.find((m) => m.listing_id === selectedId) ?? null;

  return (
    <div className="flex h-[calc(100vh-0px)] w-full bg-background">
      <RadarSidebar radars={radars} selectedId={selectedRadarId} collapsed={collapsed} onToggle={() => setCollapsed((v) => !v)} />
      <main aria-label="Mapa de oportunidades" className="relative flex flex-1 flex-col overflow-hidden">
        <div className="relative flex flex-1">
          <MapLuzSerena matches={filtered} selectedId={selectedId} hoverId={hoverId} onSelect={setSelectedId} />
          <div className="absolute left-3 top-3 bottom-3 flex w-[320px] flex-col gap-3 max-[1024px]:hidden">
            <FloatingList
              opportunities={filtered}
              selectedId={selectedId}
              hoverId={hoverId}
              filter={effectiveFilter}
              onSelect={setSelectedId}
              onHover={setHoverId}
              onFilterChange={setFilter}
            />
          </div>
          {selected && (
            <div className="absolute right-3 top-3 bottom-3 w-[380px] max-[1280px]:hidden">
              <OpportunityDetailSheet opportunity={selected as never} onClose={() => setSelectedId(null)} />
            </div>
          )}
        </div>
        {/* mobile tabs */}
        <div className="flex items-center justify-around border-t border-border p-2 lg:hidden">
          <button className="text-sm font-medium">Mapa</button>
          <button className="text-sm text-muted-foreground">Lista</button>
          <button className="text-sm text-muted-foreground" onClick={() => setChatCollapsed((v) => !v)}>
            Chat
          </button>
        </div>
      </main>
      <aside
        aria-label="Conversación del radar"
        className={cn("flex flex-col border-l border-border bg-card", chatCollapsed ? "hidden xl:hidden" : "w-[400px] max-[1280px]:hidden xl:flex")}
      >
        <div className="flex h-14 items-center justify-between border-b border-border px-4">
          <h2 className="text-sm font-semibold">Conversación</h2>
          <button className="text-xs text-muted-foreground" onClick={() => setChatCollapsed(true)} aria-label="Colapsar chat">
            »
          </button>
        </div>
        <div className="flex-1 overflow-hidden">
          {selectedRadarId ? <RadarChatPanel profileId={selectedRadarId} /> : <p className="p-4 text-sm text-muted-foreground">Seleccioná un radar.</p>}
        </div>
      </aside>
      {chatCollapsed && (
        <button className="fixed right-2 top-20 rounded bg-card p-2 shadow" onClick={() => setChatCollapsed(false)} aria-label="Expandir chat">
          Chat
        </button>
      )}
    </div>
  );
}
