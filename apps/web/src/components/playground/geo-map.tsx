"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

import type { GeoFeature } from "@/lib/playground/types";

import { categoryColorEntries } from "./geo-map-colors";

const GeoMapClient = dynamic(() => import("./geo-map-client"), {
  ssr: false,
  loading: () => <div className="min-h-96 rounded-md bg-muted/40" aria-label="Cargando mapa" />,
});

export function GeoMap({
  listing,
  features,
  selectedFeatureId,
  onFeatureSelect,
  onMapPointSelect,
}: Readonly<{
  listing: Record<string, unknown>;
  features: GeoFeature[];
  selectedFeatureId: string | null;
  onFeatureSelect: (featureId: string) => void;
  onMapPointSelect?: (point: { latitude: number; longitude: number }) => void;
}>): React.ReactElement {
  const latitude = typeof listing.latitude === "number" ? listing.latitude : -34.5875;
  const longitude = typeof listing.longitude === "number" ? listing.longitude : -58.3971;
  const poiColors = categoryColorEntries(
    features.filter((feature) => feature.kind === "poi").map((feature) => feature.category),
  );
  const [hiddenPoiCategories, setHiddenPoiCategories] = useState<string[]>([]);
  const visiblePoiCategories = poiColors
    .map(({ category }) => category)
    .filter((category) => !hiddenPoiCategories.includes(category));

  return (
    <div className="flex min-h-96 flex-col gap-2 rounded-md border border-border bg-muted/20 p-2">
      <GeoMapClient
        latitude={latitude}
        longitude={longitude}
        features={features}
        selectedFeatureId={selectedFeatureId}
        onFeatureSelect={onFeatureSelect}
        onMapPointSelect={onMapPointSelect}
        isPointInspection={listing.selection === "map_point"}
        visibleCategories={visiblePoiCategories}
        visibleCategoriesKey={visiblePoiCategories.join("\u0000")}
      />
      {poiColors.length > 0 ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-[11px] text-muted-foreground" aria-label="Leyenda de categorías de POIs">
          {poiColors.map(({ category, color }) => (
            <button
              aria-label={`${hiddenPoiCategories.includes(category) ? "Mostrar" : "Ocultar"} ${category.replaceAll("_", " ")}`}
              aria-pressed={!hiddenPoiCategories.includes(category)}
              className={`inline-flex items-center gap-1.5 rounded px-1 py-0.5 transition-opacity hover:bg-muted ${hiddenPoiCategories.includes(category) ? "opacity-40" : ""}`}
              key={category}
              onClick={() => {
                setHiddenPoiCategories((current) => current.includes(category)
                  ? current.filter((item) => item !== category)
                  : [...current, category]);
              }}
              type="button"
            >
              <span
                className="size-2.5 rounded-full border border-background shadow-sm"
                style={{ backgroundColor: color }}
                aria-hidden="true"
              />
              {category.replaceAll("_", " ")}
            </button>
          ))}
        </div>
      ) : null}
      <p className="px-1 text-xs text-muted-foreground" aria-live="polite">
        Click en un área vacía para inspeccionar ese punto. Hover sobre un POI para ver sus datos; click para fijarlos. © OpenStreetMap contributors.
      </p>
    </div>
  );
}
