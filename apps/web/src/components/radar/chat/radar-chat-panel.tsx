"use client";

import { ChatPanel } from "@/components/chat/chat-panel";

export function RadarChatPanel({ profileId }: Readonly<{ profileId: string }>) {
  const isMock = process.env.NEXT_PUBLIC_USE_MOCKS === "1";
  if (isMock) {
    return (
      <div className="flex h-full flex-col p-4">
        <div className="rounded-xl border bg-muted/30 p-4">
          <p className="text-sm font-medium">Copiloto para encontrar tu próximo lugar</p>
          <p className="mt-1 text-xs text-muted-foreground">Preguntá en lenguaje natural y te muestro el porqué.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className="rounded-full bg-background px-3 py-1 text-xs shadow hover:bg-muted">Busco 2 amb en Palermo con balcón</button>
            <button type="button" className="rounded-full bg-background px-3 py-1 text-xs shadow hover:bg-muted">Cerca de subte D, hasta $650k</button>
            <button type="button" className="rounded-full bg-background px-3 py-1 text-xs shadow hover:bg-muted">Que acepte mascotas</button>
          </div>
        </div>
        <div className="mt-4 space-y-3">
          <div className="rounded-lg bg-card p-3 shadow-sm border">
            <p className="text-xs text-muted-foreground">Umbral</p>
            <p className="text-sm">Encontré 8 oportunidades que vale la pena mirar. Todas respetan tu presupuesto; 2 están un poco más lejos del subte.</p>
          </div>
        </div>
        <p className="mt-auto px-1 py-2 text-xs text-muted-foreground">Vista previa sin backend. El mapa se mueve sin cambiar tus filtros.</p>
      </div>
    );
  }
  return (
    <div className="flex h-full flex-col">
      <ChatPanel profileId={profileId} onDecisionApplied={() => {}} />
      <p className="px-4 py-2 text-xs text-muted-foreground">El mapa se mueve sin cambiar filtros.</p>
    </div>
  );
}
