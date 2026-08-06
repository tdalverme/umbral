"use client";

import dynamic from "next/dynamic";
import { useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import type { MatchItem } from "@/lib/radar/client";

const MapLibreMap = dynamic(() => import("./maplibre-map"), {
  ssr: false,
  loading: () => <div className="h-full min-h-64 rounded-md bg-muted/40" aria-hidden />,
});

export interface MapPoint {
  listing_id: string;
  latitude: number;
  longitude: number;
  geo_precision: string;
}

export function RadarMap({
  points,
  selectedListingId,
  onSelect,
}: Readonly<{
  points: MapPoint[];
  selectedListingId: string | null;
  onSelect: (listingId: string) => void;
}>): React.ReactElement {
  const [tileError, setTileError] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  if (tileError) {
    return (
      <Alert role="alert">
        No se pudo cargar el mapa. La lista sigue disponible; intentá de nuevo más tarde.
        <button
          className="ml-2 underline"
          onClick={() => setTileError(false)}
          type="button"
        >
          Reintentar
        </button>
      </Alert>
    );
  }

  return (
    <div ref={containerRef} className="h-full min-h-64 rounded-md border border-border" aria-label="Mapa de resultados">
      <MapLibreMap
        points={points}
        selectedListingId={selectedListingId}
        onSelect={onSelect}
        onTileError={() => setTileError(true)}
      />
      <p className="sr-only">El mapa muestra solo puntos con precisión geográfica autorizada.</p>
    </div>
  );
}

export function matchPoints(items: MatchItem[]): MapPoint[] {
  return items
    .filter((item) => item.geometry !== null && item.geometry !== undefined)
    .map((item) => ({
      listing_id: item.listing_id,
      latitude: item.geometry![0],
      longitude: item.geometry![1],
      geo_precision: item.geo_precision ?? "unknown",
    }));
}

// Re-export for tree-shaking friendliness with dynamic import.
export default RadarMap;
