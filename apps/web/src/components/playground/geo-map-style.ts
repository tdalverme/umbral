import type * as maplibregl from "maplibre-gl";

import { categoryColorExpression } from "./geo-map-colors";

type MapStyleSurface = Pick<maplibregl.Map, "isStyleLoaded" | "getLayer" | "getSource" | "setPaintProperty" | "on" | "once" | "off">;

export function scheduleFeatureSourceData(
  map: MapStyleSurface,
  sourceId: string,
  data: unknown,
): () => void {
  const apply = () => {
    const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
    if (!source) return;
    source.setData(data as never);
    cleanup();
  };

  let cleanup = () => undefined;

  if (map.isStyleLoaded()) {
    apply();
    return () => undefined;
  }

  const onSourceData = (event: { sourceId?: string }) => {
    if (event.sourceId !== sourceId) return;
    apply();
  };
  map.on("sourcedata", onSourceData);
  cleanup = () => {
    map.off("sourcedata", onSourceData);
  };
  return cleanup;
}

export function scheduleCategoryPaint(
  map: MapStyleSurface,
  categories: readonly string[],
): () => void {
  const apply = () => {
    if (!map.isStyleLoaded() || !map.getLayer("urban-points")) return;
    map.setPaintProperty("urban-points", "circle-color", categoryColorExpression(categories) as never);
  };

  if (map.isStyleLoaded()) {
    apply();
    return () => undefined;
  }

  map.once("load", apply);
  return () => map.off("load", apply);
}

export function scheduleSelectedFeaturePaint(
  map: MapStyleSurface,
  selectedFeatureId: string | null,
): () => void {
  const apply = () => {
    if (!selectedFeatureId || !map.isStyleLoaded() || !map.getLayer("urban-points")) return;
    map.setPaintProperty("urban-points", "circle-radius", [
      "case",
      ["==", ["get", "id"], selectedFeatureId],
      10,
      7,
    ]);
  };

  if (map.isStyleLoaded()) {
    apply();
    return () => undefined;
  }

  map.once("load", apply);
  return () => map.off("load", apply);
}
