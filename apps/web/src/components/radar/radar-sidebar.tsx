"use client";

import Link from "next/link";
import { useState } from "react";

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

  return (
    <nav aria-label="Radares" className={cn("flex flex-col border-r border-border bg-card", collapsed ? "w-16" : "w-[280px]")}>
      <div className="flex h-14 items-center justify-between border-b border-border px-3">
        {!collapsed && <BrandLogo layout="horizontal" tone="dark" className="h-6 w-auto" />}
        {collapsed && <BrandLogo layout="symbol" tone="dark" className="h-7 w-7" />}
        <Button aria-label={collapsed ? "Expandir radares" : "Colapsar radares"} onClick={onToggle} className="h-8 w-8 p-0 text-xs">
          {collapsed ? "»" : "«"}
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        <div className="mb-2 flex items-center justify-between px-2">
          {!collapsed && <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Radares</span>}
          <Link href="/radar/new" aria-label="Crear radar">
            <Button className="h-7 w-7 p-0 text-xs">+</Button>
          </Link>
        </div>
        <ul className="space-y-1" role="list">
          {radars.map((r) => (
            <li key={r.search_profile_id}>
              {editingId === r.search_profile_id ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (draft.trim().length >= 3) {
                      onRename?.(r.search_profile_id, draft.trim());
                      setEditingId(null);
                    }
                  }}
                  className="flex gap-1 px-2"
                >
                  <input value={draft} onChange={(e) => setDraft(e.target.value)} className="w-full rounded border px-2 py-1 text-sm" autoFocus />
                  <Button type="submit" className="h-7 px-2 text-xs">
                    OK
                  </Button>
                </form>
              ) : (
                <Link
                  href={`/radar/${r.search_profile_id}`}
                  className={cn(
                    "flex items-center justify-between rounded-md px-3 py-2 text-sm hover:bg-muted",
                    selectedId === r.search_profile_id && "bg-muted font-medium",
                  )}
                  aria-current={selectedId === r.search_profile_id ? "page" : undefined}
                >
                  <span className="truncate">{collapsed ? r.name.slice(0, 1).toUpperCase() : r.name}</span>
                  {!collapsed && <span className="text-xs text-muted-foreground">{r.status}</span>}
                </Link>
              )}
              {!collapsed && editingId !== r.search_profile_id && (
                <button
                  className="ml-2 text-xs text-muted-foreground hover:underline"
                  onClick={() => {
                    setEditingId(r.search_profile_id);
                    setDraft(r.name);
                  }}
                >
                  editar
                </button>
              )}
            </li>
          ))}
        </ul>
        {radars.length === 0 && !collapsed && <p className="px-3 py-4 text-sm text-muted-foreground">No hay radares todavía.</p>}
      </div>
    </nav>
  );
}
