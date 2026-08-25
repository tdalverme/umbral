import { describe, expect, it } from "vitest";

import type { GeoFeature } from "@/lib/playground/types";

import { poiMarkerData } from "./geo-map-markers";

describe("poiMarkerData", () => {
  it("returns only point POIs with their map coordinates and category color", () => {
    const features = [
      {
        id: "cafe-1",
        name: "Café",
        category: "cafe",
        kind: "poi",
        geometry: { type: "Point", coordinates: [-58.4, -34.5] },
      },
      {
        id: "road-1",
        name: "Avenida",
        category: "major_road",
        kind: "linear",
        geometry: { type: "LineString", coordinates: [[-58.4, -34.5], [-58.41, -34.51]] },
      },
      {
        id: "invalid-1",
        name: "Sin geometría",
        category: "park",
        kind: "poi",
        geometry: null,
      },
    ] satisfies GeoFeature[];

    expect(poiMarkerData(features)).toEqual([
      { featureId: "cafe-1", longitude: -58.4, latitude: -34.5, color: "#e05252" },
    ]);
  });

  it("can hide categories without changing the color assigned to the remaining marker", () => {
    const features = [
      {
        id: "cafe-1",
        name: "Café",
        category: "cafe",
        kind: "poi",
        geometry: { type: "Point", coordinates: [-58.4, -34.5] },
      },
      {
        id: "park-1",
        name: "Parque",
        category: "park",
        kind: "poi",
        geometry: { type: "Point", coordinates: [-58.41, -34.51] },
      },
    ] satisfies GeoFeature[];

    expect(poiMarkerData(features, ["cafe"])).toEqual([
      { featureId: "cafe-1", longitude: -58.4, latitude: -34.5, color: "#e05252" },
    ]);
  });
});
