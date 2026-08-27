"use client";

import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type { MatchItem } from "@/lib/radar/client";
import { viewportOptions } from "@/lib/map/motion";
import { groupWithOffsets } from "./pin-offset";

const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

export function MapLuzSerena({
  matches,
  selectedId,
  hoverId,
  onSelect,
}: Readonly<{
  matches: MatchItem[];
  selectedId: string | null;
  hoverId: string | null;
  onSelect: (id: string | null) => void;
}>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const points = matches
    .filter((m) => Array.isArray(m.geometry) && m.geometry.length === 2)
    .map((m) => ({ id: m.listing_id, lng: (m.geometry as [number, number])[0], lat: (m.geometry as [number, number])[1] }));

  const withOffsets = groupWithOffsets(points);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: { type: "raster", tiles: [TILE_URL], tileSize: 256, attribution: "© OpenStreetMap contributors" },
          opportunities: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
        },
        layers: [
          { id: "background", type: "background", paint: { "background-color": "#F4EFE6" } },
          { id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.82 } },
          {
            id: "opportunity-points",
            type: "circle",
            source: "opportunities",
            paint: {
              "circle-color": "#293F38",
              "circle-radius": 7,
              "circle-stroke-color": "#FFFAF2",
              "circle-stroke-width": 1.5,
              "circle-opacity": 0.95,
            },
          },
        ],
      },
      center: [-58.3816, -34.6037],
      zoom: 12,
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const features = withOffsets.map((p) => ({
      type: "Feature" as const,
      id: p.id,
      properties: { id: p.id, selected: p.id === selectedId, hover: p.id === hoverId },
      geometry: { type: "Point" as const, coordinates: [p.lng + p.offset.x, p.lat + p.offset.y] as [number, number] },
    }));
    const source = map.getSource("opportunities") as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData({ type: "FeatureCollection", features: features as never[] });
    }
    // paint for selected
    if (map.isStyleLoaded() && map.getLayer("opportunity-points")) {
      map.setPaintProperty("opportunity-points", "circle-color", [
        "case",
        ["==", ["get", "id"], selectedId ?? ""],
        "#DE6D4A",
        "#293F38",
      ] as never);
      map.setPaintProperty("opportunity-points", "circle-radius", [
        "case",
        ["==", ["get", "id"], hoverId ?? ""],
        9,
        ["==", ["get", "id"], selectedId ?? ""],
        10,
        7,
      ] as never);
    }
    if (selectedId) {
      const sel = withOffsets.find((p) => p.id === selectedId);
      if (sel) {
        const opts = viewportOptions([sel.lng, sel.lat], 16, "selección oportunidad");
        if (opts.animated) map.flyTo({ center: opts.center, zoom: opts.zoom, duration: opts.duration });
        else map.jumpTo({ center: opts.center, zoom: opts.zoom });
      }
    }
  }, [withOffsets, selectedId, hoverId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const handler = (e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
      const f = e.features?.[0];
      const id = f?.properties?.id as string | undefined;
      if (id) onSelect(id);
    };
    map.on("click", "opportunity-points", handler as never);
    return () => {
      map.off("click", "opportunity-points", handler as never);
    };
  }, [onSelect]);

  if (withOffsets.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center bg-[var(--brand-linen)] text-sm text-muted-foreground" aria-label="Mapa de oportunidades">
        Mapa listo — seleccioná una oportunidad para centrar.
      </div>
    );
  }

  return <div ref={containerRef} className="flex-1" aria-label="Mapa de oportunidades" role="region" />;
}
