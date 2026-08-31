"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { BrandLogo } from "@/components/brand/brand-logo";
import { cn } from "@/lib/utils";
import type { SearchProfile } from "@/lib/radar/client";

export function RadarSidebar({
  radars,
  selectedId,
  collapsed,
  onToggle,
  onRename,
}: Readonly<{
  radars: SearchProfile[];
  selectedId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  onRename?: (id: string, name: string) => void;
}>) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [isHovered, setIsHovered] = useState(false);

  // Hover expande temporalmente; si está pineada (collapsed=false) queda expandida
  const effectiveCollapsed = collapsed && !isHovered;

  useEffect(() => {
    const dispatch = () => window.dispatchEvent(new Event("resize"));
    dispatch();
    const t1 = window.setTimeout(dispatch, 160);
    const t2 = window.setTimeout(dispatch, 340);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [effectiveCollapsed]);

  return (
    <nav
      aria-label="Radares"
      data-collapsed={effectiveCollapsed ? "true" : "false"}
      onMouseEnter={() => {
        if (collapsed) setIsHovered(true);
      }}
      onMouseLeave={() => setIsHovered(false)}
      className={cn(
        "relative flex shrink-0 flex-col border-r border-border bg-card overflow-hidden",
        "motion-safe:transition-[width] motion-safe:duration-[320ms] motion-safe:ease-[cubic-bezier(0.32,0.08,0.24,1)]",
        effectiveCollapsed ? "w-[64px]" : "w-[280px]",
      )}
    >
      <div className="flex h-full w-full flex-col overflow-hidden">
        {/* Header — misma barra que se expande, sin fade a otra */}
        <div
          className={cn(
            "flex h-14 shrink-0 items-center border-b border-border overflow-hidden",
            "motion-safe:transition-[padding] motion-safe:duration-[320ms] motion-safe:ease-[cubic-bezier(0.32,0.08,0.24,1)]",
            effectiveCollapsed ? "justify-center px-2" : "justify-between px-3",
          )}
        >
          {effectiveCollapsed ? (
            <button
              type="button"
              aria-label="Expandir radares"
              onClick={onToggle}
              className="inline-flex items-center justify-center rounded-lg p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
            >
              <BrandLogo layout="symbol" tone="dark" className="h-7 w-7 shrink-0" />
            </button>
          ) : (
            <>
              <BrandLogo layout="horizontal" tone="dark" className="h-5 w-auto shrink-0" />
              <button
                type="button"
                aria-label={collapsed ? "Fijar expandido" : "Colapsar radares"}
                onClick={onToggle}
                className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground shadow-xs transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card active:scale-[0.97]"
              >
                <span aria-hidden className="text-sm leading-none">
                  {collapsed ? "»" : "«"}
                </span>
              </button>
            </>
          )}
        </div>

        {/* Botón expandir inline — dentro del rail, sin overflow sobre el mapa */}
        <div
          className={cn(
            "flex shrink-0 items-center justify-center overflow-hidden border-b border-border/60 bg-card",
            "motion-safe:transition-[height,opacity] motion-safe:duration-[280ms] motion-safe:ease-[cubic-bezier(0.32,0.08,0.24,1)]",
            effectiveCollapsed ? "h-[48px] opacity-100" : "h-0 opacity-0 pointer-events-none border-b-0",
          )}
          aria-hidden={!effectiveCollapsed}
        >
          <button
            type="button"
            aria-label="Expandir radares"
            onClick={onToggle}
            tabIndex={effectiveCollapsed ? 0 : -1}
            className="inline-flex size-8 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground shadow-sm transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card active:scale-[0.97]"
          >
            <span aria-hidden className="text-sm leading-none">
              »
            </span>
          </button>
        </div>

        {/* Section header — mismo elemento que se comprime */}
        <div
          className={cn(
            "flex shrink-0 items-center overflow-hidden",
            "motion-safe:transition-[padding] motion-safe:duration-[280ms] motion-safe:ease-[cubic-bezier(0.32,0.08,0.24,1)]",
            effectiveCollapsed ? "justify-center px-2 py-2.5" : "justify-between px-3 py-3",
          )}
        >
          <span
            className={cn(
              "whitespace-nowrap text-xs font-medium uppercase tracking-wide text-muted-foreground overflow-hidden",
              "motion-safe:transition-[max-width,opacity,transform] motion-safe:duration-[240ms] motion-safe:ease-[cubic-bezier(0.32,0.08,0.24,1)]",
              effectiveCollapsed ? "max-w-0 opacity-0 -translate-x-1 pointer-events-none" : "max-w-[100px] opacity-100 translate-x-0",
            )}
            aria-hidden={effectiveCollapsed}
          >
            Radares
          </span>
          <Link
            href="/radar/new"
            aria-label="Crear radar"
            className="inline-flex size-7 shrink-0 items-center justify-center rounded-md bg-muted text-foreground shadow-xs transition-colors hover:bg-muted/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card active:scale-[0.97]"
          >
            <span aria-hidden className="text-sm leading-none">
              +
            </span>
          </Link>
        </div>

        {/* Lista — única, el texto se recorta por el width del sidebar, sin lista duplicada */}
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className={cn("flex-1 overflow-y-auto overflow-x-hidden pb-4", effectiveCollapsed ? "px-1.5" : "px-2")}>
            <ul className="space-y-1" role="list">
              {radars.map((r) => {
                const isActive = selectedId === r.search_profile_id;
                const isEditing = editingId === r.search_profile_id;

                if (isEditing) {
                  return (
                    <li key={r.search_profile_id} className="px-1 py-1">
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          if (draft.trim().length >= 3) {
                            onRename?.(r.search_profile_id, draft.trim());
                            setEditingId(null);
                          }
                        }}
                        className="flex items-center gap-1.5"
                      >
                        <input
                          value={draft}
                          onChange={(e) => setDraft(e.target.value)}
                          className="h-8 w-full rounded-md border border-input bg-background px-2.5 py-1 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card"
                          autoFocus
                          aria-label="Nuevo nombre del radar"
                          placeholder="Nombre del radar"
                        />
                        <Button type="submit" className="h-8 shrink-0 px-3 text-xs">
                          OK
                        </Button>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="inline-flex h-8 shrink-0 items-center justify-center rounded-md px-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                          aria-label="Cancelar edición"
                        >
                          ✕
                        </button>
                      </form>
                    </li>
                  );
                }

                return (
                  <li key={r.search_profile_id} className="group/item flex items-center gap-1">
                    <Link
                      href={`/radar/${r.search_profile_id}`}
                      title={r.name}
                      aria-current={isActive ? "page" : undefined}
                      aria-label={effectiveCollapsed ? `${r.name} — ${r.status}` : undefined}
                      className={cn(
                        "flex min-w-0 flex-1 items-center gap-2 rounded-lg text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card",
                        "motion-safe:transition-[background-color,color,box-shadow] motion-safe:duration-200",
                        effectiveCollapsed ? "justify-center px-1 py-1.5" : "px-2.5 py-2.5",
                        isActive
                          ? "bg-muted font-medium text-foreground shadow-xs"
                          : "text-foreground hover:bg-muted/60 hover:text-foreground",
                      )}
                    >
                      {/* Colapsado: punto minimal — más chico y perfectamente centrado */}
                      <span
                        className={cn(
                          "shrink-0 items-center justify-center overflow-hidden motion-safe:transition-[width,opacity,transform] motion-safe:duration-[280ms] motion-safe:ease-[cubic-bezier(0.32,0.08,0.24,1)]",
                          effectiveCollapsed ? "inline-flex size-6 opacity-100 scale-100" : "inline-flex size-0 opacity-0 scale-90 pointer-events-none",
                        )}
                        aria-hidden={!effectiveCollapsed}
                      >
                        <span
                          className={cn(
                            "size-1.5 rounded-full shadow-sm",
                            r.status === "active" && "bg-emerald-500",
                            r.status === "paused" && "bg-amber-500",
                            r.status === "archived" && "bg-muted-foreground/50",
                            isActive && "size-2 ring-2 ring-border bg-emerald-500",
                            isActive && r.status === "paused" && "bg-amber-500 ring-amber-500/30",
                            isActive && r.status === "archived" && "bg-muted-foreground/60",
                          )}
                        />
                      </span>

                      {/* Expandido: nombre + badge — chip siempre a la derecha, gap consistente */}
                      <span
                        className={cn(
                          "min-w-0 flex-1 items-center justify-between gap-3 overflow-hidden whitespace-nowrap",
                          "motion-safe:transition-[max-width,opacity,transform] motion-safe:duration-[280ms] motion-safe:ease-[cubic-bezier(0.32,0.08,0.24,1)]",
                          effectiveCollapsed
                            ? "flex max-w-0 opacity-0 -translate-x-1 pointer-events-none"
                            : "flex max-w-[180px] opacity-100 translate-x-0",
                        )}
                        aria-hidden={effectiveCollapsed}
                      >
                        <span className="min-w-0 flex-1 truncate font-[450] leading-tight tracking-[-0.01em]">{r.name}</span>
                        <span
                          className={cn(
                            "inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium capitalize leading-none",
                            r.status === "active" && "bg-emerald-500/10 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300",
                            r.status === "paused" && "bg-amber-500/10 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300",
                            r.status === "archived" && "bg-muted text-muted-foreground",
                          )}
                        >
                          <span
                            className={cn(
                              "size-1.5 rounded-full",
                              r.status === "active" && "bg-emerald-500",
                              r.status === "paused" && "bg-amber-500",
                              r.status === "archived" && "bg-muted-foreground/50",
                            )}
                            aria-hidden
                          />
                          {r.status}
                        </span>
                      </span>
                    </Link>

                    {!effectiveCollapsed && (
                      <button
                        type="button"
                        aria-label={`Editar ${r.name}`}
                        onClick={() => {
                          setEditingId(r.search_profile_id);
                          setDraft(r.name);
                        }}
                        className="inline-flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-foreground focus:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover/item:opacity-100"
                      >
                        <svg
                          width="14"
                          height="14"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.75"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          aria-hidden
                        >
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                          <path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>

            {radars.length === 0 && !effectiveCollapsed && (
              <div className="mx-2 mt-4 rounded-xl border border-dashed border-border bg-muted/30 px-3 py-6 text-center">
                <p className="text-sm font-medium text-foreground">Aún no tenés radares</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  Creá tu primer radar para que Umbral empiece a buscar por vos.
                </p>
                <Link
                  href="/radar/new"
                  className="mt-3 inline-flex h-8 items-center justify-center rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground shadow-xs transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Crear radar
                </Link>
              </div>
            )}

            {radars.length === 0 && effectiveCollapsed && <p className="sr-only">No hay radares todavía.</p>}
          </div>
        </div>

        {/* Footer meta — mismo elemento que colapsa en altura */}
        <div
          className={cn(
            "shrink-0 overflow-hidden border-t border-border",
            "motion-safe:transition-[height,opacity] motion-safe:duration-[260ms] motion-safe:ease-[cubic-bezier(0.32,0.08,0.24,1)]",
            effectiveCollapsed ? "h-0 border-t-0 opacity-0 pointer-events-none" : "h-auto opacity-100",
          )}
          aria-hidden={effectiveCollapsed}
        >
          {radars.length > 0 && (
            <div className="px-3 py-2.5">
              <p className="text-xs leading-relaxed text-muted-foreground">
                {radars.length} {radars.length === 1 ? "radar" : "radares"} ·{" "}
                <Link href="/radar" className="underline decoration-border underline-offset-4 hover:text-foreground hover:decoration-foreground/30">
                  ver todos
                </Link>
              </p>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
