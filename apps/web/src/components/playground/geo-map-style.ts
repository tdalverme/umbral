import type * as maplibregl from "maplibre-gl";

type MapStyleSurface = Pick<maplibregl.Map, "isStyleLoaded" | "getLayer" | "setPaintProperty" | "once" | "off">;

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
