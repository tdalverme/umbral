"use client";

import { useState } from "react";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

interface MiniCardProps {
  listingId: string;
  profileId: string;
  runId: string | null;
  onFeedback?: (text: string) => void;
}

const DISLIKE_REASONS: { key: string; label: string }[] = [
  { key: "price_too_high", label: "Precio alto" },
  { key: "expensas_high", label: "Expensas altas" },
  { key: "location_no", label: "Ubicación" },
  { key: "rooms_wrong", label: "Ambientes" },
  { key: "surface_wrong", label: "Superficie chica" },
  { key: "building_state", label: "Estado del edificio" },
  { key: "lighting_bad", label: "Poca luz" },
  { key: "other", label: "Otra razón" },
];

const LIKE_REASONS: { key: string; label: string }[] = [
  { key: "price_fits", label: "Precio acorde" },
  { key: "location_yes", label: "Ubicación" },
  { key: "balcony_wanted", label: "Quiero balcón" },
  { key: "access_ok", label: "Buen transporte" },
  { key: "other", label: "Otra razón" },
];

/** Persistent, navigable reference to a listing (FR-031): links to the radar
 * detail and offers quick like/dislike reasons that feed the chat (Fase 2). */
export function MiniCard({
  listingId,
  profileId,
  runId,
  onFeedback,
}: MiniCardProps): React.ReactElement {
  const [mode, setMode] = useState<"like" | "dislike" | null>(null);
  const query = new URLSearchParams({ profile: profileId });
  if (runId) query.set("run", runId);

  function send(reasonLabel: string): void {
    if (!onFeedback) return;
    const verb = mode === "dislike" ? "No me gusta" : "Me gusta";
    onFeedback(`${verb} este depto ${listingId}, ${reasonLabel.toLowerCase()}`);
    setMode(null);
  }

  return (
    <Card data-testid="mini-card" className="border-border/60 p-2">
      <p className="text-xs text-muted-foreground">Oportunidad de tu radar</p>
      <Link
        href={`/listings/${listingId}?${query.toString()}`}
        className="text-sm font-medium underline-offset-4 hover:underline"
        aria-label={`Ver ficha del depto ${listingId.slice(0, 8)} en tu radar`}
      >
        Ver ficha
      </Link>
      {onFeedback && mode === null && (
        <div className="mt-2 flex gap-2">
          <Button
            className="min-h-9 px-3 py-2 text-xs"
            onClick={() => setMode("like")}
          >
            Me gusta
          </Button>
          <Button
            className="min-h-9 px-3 py-2 text-xs"
            onClick={() => setMode("dislike")}
          >
            No me gusta
          </Button>
        </div>
      )}
      {onFeedback && mode !== null && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {(mode === "dislike" ? DISLIKE_REASONS : LIKE_REASONS).map((reason) => (
            <Button
              key={reason.key}
              className="min-h-9 border border-border bg-background px-3 py-2 text-xs text-foreground hover:bg-muted"
              onClick={() => send(reason.label)}
            >
              {reason.label}
            </Button>
          ))}
        </div>
      )}
    </Card>
  );
}
