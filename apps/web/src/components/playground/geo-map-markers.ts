import type { GeoFeature } from "@/lib/playground/types";

import { categoryColorEntries } from "./geo-map-colors";

export interface PoiMarkerData {
  featureId: string;
  longitude: number;
  latitude: number;
  color: string;
}

function pointCoordinates(feature: GeoFeature): [number, number] | null {
  if (feature.kind !== "poi" || feature.geometry?.type !== "Point") return null;
  const coordinates = feature.geometry.coordinates;
  if (!Array.isArray(coordinates) || coordinates.length < 2) return null;
  const [longitude, latitude] = coordinates;
  if (typeof longitude !== "number" || typeof latitude !== "number") return null;
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return null;
  return [longitude, latitude];
}

export function poiMarkerData(
  features: readonly GeoFeature[],
  visibleCategories?: readonly string[],
): PoiMarkerData[] {
  const pointFeatures = features.flatMap((feature) => {
    const coordinates = pointCoordinates(feature);
    return coordinates ? [{ feature, coordinates }] : [];
  });
  const visibleCategorySet = visibleCategories === undefined ? null : new Set(visibleCategories);
  const colors = new Map(
    categoryColorEntries(pointFeatures.map(({ feature }) => feature.category)).map(({ category, color }) => [category, color]),
  );

  return pointFeatures
    .filter(({ feature }) => visibleCategorySet === null || visibleCategorySet.has(feature.category))
    .map(({ feature, coordinates: [longitude, latitude] }) => ({
      featureId: feature.id,
      longitude,
      latitude,
      color: colors.get(feature.category) ?? "#64748b",
    }));
}
