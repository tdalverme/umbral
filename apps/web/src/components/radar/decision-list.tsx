"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { radarApi, type DecisionItem, type FeedbackEventType } from "@/lib/radar/client";

const TITLE: Record<string, string> = {
  save: "Guardados",
  dismiss: "Descartados",
};

export function DecisionList({
  profileId,
  decisionState,
  onViewed,
}: {
  profileId: string;
  decisionState: FeedbackEventType;
  onViewed?: (count: number) => void;
}): React.ReactElement {
  const [items, setItems] = useState<DecisionItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    radarApi
      .decisionItems(profileId, decisionState)
      .then((page) => {
        setItems(page.items);
        setError(null);
        onViewed?.(page.items.length);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "feedback.error");
      });
  }, [profileId, decisionState, onViewed]);

  if (items === null && error === null) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground">
        <Spinner /> Cargando {TITLE[decisionState]}…
      </div>
    );
  }

  if (error) {
    return (
      <Alert role="alert">
        No se pudieron cargar los {TITLE[decisionState]} ({error}).
      </Alert>
    );
  }

  if (items === null || items.length === 0) {
    return (
      <Card>
        <CardContent className="py-6 text-sm text-muted-foreground">
          Todavía no hay {TITLE[decisionState].toLowerCase()}.{" "}
          <Link href={`/radar/${profileId}`} className="underline">
            Volver al radar
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <ul className="space-y-3">
      {items.map((item) => (
        <li key={item.event_id}>
          <Link href={`/listings/${item.listing_id}?profile=${profileId}`}>
            <Card className="transition-colors hover:border-ring" data-testid="decision-item">
              <CardContent className="flex items-center justify-between gap-4 py-4">
                <div>
                  <p className="font-medium">
                    {item.neighborhood ?? "Barrio no declarado"} · ${Number(item.total_cost ?? 0).toLocaleString("es-AR")}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {item.surface_m2 !== null ? `${item.surface_m2} m²` : "superficie no declarada"} ·{" "}
                    {item.rooms !== null ? `${item.rooms} ambientes` : "ambientes no declarados"} ·{" "}
                    {item.source_id ?? "fuente no declarada"}
                  </p>
                  {item.reason_keys.length > 0 && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      razones: {item.reason_keys.map((key) => key.replace(/_/g, " ")).join(", ")}
                    </p>
                  )}
                </div>
                <Button className="bg-muted text-foreground hover:bg-muted/80">Ver detalle</Button>
              </CardContent>
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}
