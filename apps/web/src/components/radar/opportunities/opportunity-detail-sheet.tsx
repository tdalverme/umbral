"use client";

import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { snapshotBadge, formatDistance } from "@/lib/urban/signal-meta";

export function OpportunityDetailSheet({
  opportunity,
  onClose,
}: Readonly<{
  opportunity: { listing_id: string; neighborhood: string | null; total_cost: number | null; surface_m2: number | null; rooms: number | null };
  onClose: () => void;
}>) {
  const ref = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  return (
    <Card className="flex h-full flex-col overflow-hidden shadow-lg">
      <CardHeader className="border-b">
        <div className="flex items-start justify-between">
          <h2 ref={ref} tabIndex={-1} className="text-lg font-semibold outline-none">
            {opportunity.neighborhood ?? "Oportunidad"} — ${Number(opportunity.total_cost ?? 0).toLocaleString("es-AR")}
          </h2>
          <Button aria-label="Cerrar detalle" onClick={onClose} className="h-8 w-8 p-0">
            ×
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          {opportunity.surface_m2 ?? "—"} m² · {opportunity.rooms ?? "—"} ambientes
        </p>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto space-y-4 p-4">
        <section>
          <h3 className="text-sm font-semibold">Por qué encaja</h3>
          <p className="text-sm text-muted-foreground">Cercanía a lo que pediste y buena relación precio/superficie.</p>
        </section>
        <section>
          <h3 className="text-sm font-semibold">Concesiones</h3>
          <p className="text-sm text-muted-foreground">Puede requerir revisar distancia a transporte.</p>
        </section>
        <Alert>
          <AlertTitle>Incertidumbres</AlertTitle>
          <AlertDescription>No sabemos sobre luz natural — punto para consultar.</AlertDescription>
        </Alert>
        <section>
          <h3 className="text-sm font-semibold">Señales urbanas</h3>
          <ul className="space-y-1 text-xs text-muted-foreground">
            <li>Transporte 300m: 3 · 600m: 7 · {formatDistance(180)}</li>
            <li>Cafés 300m: 5 · {formatDistance(90)}</li>
            <li>Snapshot: {snapshotBadge({ date: "2026-08-20", sha256: "abc123def456" })}</li>
          </ul>
          <p className="text-[11px] text-muted-foreground">Fuente OSM via contrato v2 · atribución © OpenStreetMap</p>
        </section>
        <div className="flex gap-2">
          <Button className="h-8 px-3 text-xs">Ver</Button>
          <Button className="h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80">Guardar</Button>
          <Button className="h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80">Descartar</Button>
          <Button className="h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80" onClick={onClose}>
            Esc
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">Feedback por concepto: suave reordena, hard excluye con confirmación.</p>
      </CardContent>
    </Card>
  );
}
