"use client";

import * as maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";

import "maplibre-gl/dist/maplibre-gl.css";

import type { MapPoint } from "./map";

const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

export default function MaplibreMap({
  points,
  selectedListingId,
  onSelect,
  onTileError,
}: Readonly<{
  points: MapPoint[];
  selectedListingId: string | null;
  onSelect: (listingId: string) => void;
  onTileError: () => void;
}>): React.ReactElement | null {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<Array<maplibregl.Marker | maplibregl.Popup>>([]);
  const tileErrorRef = useRef(onTileError);

  useEffect(() => {
    tileErrorRef.current = onTileError;
  }, [onTileError]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: { type: "raster", tiles: [TILE_URL], tileSize: 256, attribution: ATTRIBUTION },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: [-58.3816, -34.6037],
      zoom: 11,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("error", () => tileErrorRef.current());
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];
    points.forEach((point) => {
      const element = document.createElement("button");
      element.setAttribute("aria-label", `Propiedad en ${point.geo_precision}`);
      element.dataset.listingId = point.listing_id;
      element.className = "size-3 rounded-full border-2 border-white bg-primary";
      const marker = new maplibregl.Marker({ element }).setLngLat([point.longitude, point.latitude]);
      marker.getElement().addEventListener("click", () => onSelect(point.listing_id));
      marker.addTo(map);
      markersRef.current.push(marker);
    });
  }, [points, selectedListingId, onSelect]);

  useEffect(() => {
    markersRef.current.forEach((marker) => {
      if (marker instanceof maplibregl.Marker) {
        const listingId = marker.getElement().dataset.listingId;
        marker.getElement().classList.toggle("ring-2", listingId === selectedListingId);
      }
    });
  }, [selectedListingId]);

  return <div ref={containerRef} className="h-full min-h-64 w-full" />;
}
