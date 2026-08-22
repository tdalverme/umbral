"use client";

import dynamic from "next/dynamic";

import type { GeoFeature } from "@/lib/playground/types";

const GeoMapClient = dynamic(() => import("./geo-map-client"), {
  ssr: false,
  loading: () => <div className="min-h-96 rounded-md bg-muted/40" aria-label="Cargando mapa" />,
});

export function GeoMap({
  listing,
  features,
  selectedFeatureId,
  onFeatureSelect,
}: Readonly<{
  listing: Record<string, unknown>;
  features: GeoFeature[];
  selectedFeatureId: string | null;
  onFeatureSelect: (featureId: string) => void;
}>): React.ReactElement {
  const latitude = typeof listing.latitude === "number" ? listing.latitude : -34.5875;
  const longitude = typeof listing.longitude === "number" ? listing.longitude : -58.3971;

  return (
    <div className="flex min-h-96 flex-col gap-2 rounded-md border border-border bg-muted/20 p-2">
      <GeoMapClient
        latitude={latitude}
        longitude={longitude}
        features={features}
        selectedFeatureId={selectedFeatureId}
        onFeatureSelect={onFeatureSelect}
      />
      <p className="px-1 text-xs text-muted-foreground" aria-live="polite">
        Click en un POI o línea para inspeccionar su aporte. © OpenStreetMap contributors.
      </p>
    </div>
  );
}

