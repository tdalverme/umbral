"use client";

import * as maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";

import "maplibre-gl/dist/maplibre-gl.css";

import type { GeoFeature } from "@/lib/playground/types";

const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const SOURCE_ID = "playground-urban-features";

function featureCollection(features: GeoFeature[]) {
  return {
    type: "FeatureCollection" as const,
    features: features.flatMap((feature) => {
      const geometry = feature.geometry;
      if (!geometry || typeof geometry.type !== "string") return [];
      return [{
        type: "Feature" as const,
        id: feature.id,
        properties: {
          id: feature.id,
          name: feature.name,
          category: feature.category,
          kind: feature.kind,
          distance_m: feature.distance_m,
        },
        geometry: geometry as never,
      }];
    }),
  };
}

export default function GeoMapClient({
  latitude,
  longitude,
  features,
  selectedFeatureId,
  onFeatureSelect,
}: Readonly<{
  latitude: number;
  longitude: number;
  features: GeoFeature[];
  selectedFeatureId: string | null;
  onFeatureSelect: (featureId: string) => void;
}>): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const selectRef = useRef(onFeatureSelect);

  useEffect(() => {
    selectRef.current = onFeatureSelect;
  }, [onFeatureSelect]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: [TILE_URL],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
          [SOURCE_ID]: { type: "geojson", data: featureCollection([]) },
        },
        layers: [
          { id: "osm", type: "raster", source: "osm" },
          {
            id: "urban-lines",
            type: "line",
            source: SOURCE_ID,
            filter: ["==", ["get", "kind"], "linear"],
            paint: { "line-color": "#334155", "line-width": 3, "line-opacity": 0.72 },
          },
          {
            id: "urban-points",
            type: "circle",
            source: SOURCE_ID,
            filter: ["==", ["get", "kind"], "poi"],
            paint: {
              "circle-color": "#0f766e",
              "circle-radius": 7,
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 1.5,
            },
          },
        ],
      },
      center: [longitude, latitude],
      zoom: 14,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("click", "urban-points", (event) => {
      const feature = event.features?.[0];
      const id = feature?.properties?.id;
      if (typeof id === "string") selectRef.current(id);
    });
    map.on("click", "urban-lines", (event) => {
      const feature = event.features?.[0];
      const id = feature?.properties?.id;
      if (typeof id === "string") selectRef.current(id);
    });
    map.on("mouseenter", "urban-points", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseenter", "urban-lines", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "urban-points", () => { map.getCanvas().style.cursor = ""; });
    map.on("mouseleave", "urban-lines", () => { map.getCanvas().style.cursor = ""; });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [latitude, longitude]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const source = map.getSource(SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    source?.setData(featureCollection(features) as never);
    markerRef.current?.remove();
    const element = document.createElement("div");
    element.className = "size-4 rounded-full border-2 border-primary-foreground bg-primary shadow-md";
    element.setAttribute("aria-label", "Listing seleccionado");
    markerRef.current = new maplibregl.Marker({ element }).setLngLat([longitude, latitude]).addTo(map);
    map.setCenter([longitude, latitude]);
  }, [features, latitude, longitude]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!selectedFeatureId) return;
    map.setPaintProperty("urban-points", "circle-radius", [
      "case",
      ["==", ["get", "id"], selectedFeatureId],
      10,
      7,
    ]);
  }, [selectedFeatureId]);

  return <div ref={containerRef} className="min-h-80 w-full flex-1" aria-label="Mapa de contexto urbano" />;
}

