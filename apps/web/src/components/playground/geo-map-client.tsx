"use client";

import * as maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";

import "maplibre-gl/dist/maplibre-gl.css";

import type { GeoFeature } from "@/lib/playground/types";

import { poiMarkerData } from "./geo-map-markers";
import { scheduleFeatureSourceData } from "./geo-map-style";

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

function popupContent(feature: GeoFeature): HTMLDivElement {
  const content = document.createElement("div");
  content.className = "flex min-w-40 flex-col gap-1 text-sm";

  const title = document.createElement("p");
  title.className = "font-medium text-foreground";
  title.textContent = feature.name || feature.id;

  const category = document.createElement("p");
  category.className = "text-muted-foreground";
  category.textContent = `Categoría: ${feature.category.replaceAll("_", " ")}`;

  const kind = document.createElement("p");
  kind.className = "text-muted-foreground";
  kind.textContent = `Tipo: ${feature.kind}`;

  const distance = document.createElement("p");
  distance.className = "text-muted-foreground";
  distance.textContent = `Distancia: ${typeof feature.distance_m === "number" ? `${Math.round(feature.distance_m)} m` : "sin dato"}`;

  content.append(title, category, kind, distance);
  return content;
}

export default function GeoMapClient({
  latitude,
  longitude,
  features,
  selectedFeatureId,
  onFeatureSelect,
  onMapPointSelect,
  isPointInspection,
  visibleCategories,
  visibleCategoriesKey,
}: Readonly<{
  latitude: number;
  longitude: number;
  features: GeoFeature[];
  selectedFeatureId: string | null;
  onFeatureSelect: (featureId: string) => void;
  onMapPointSelect?: (point: { latitude: number; longitude: number }) => void;
  isPointInspection: boolean;
  visibleCategories: readonly string[];
  visibleCategoriesKey: string;
}>): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const poiMarkersRef = useRef<maplibregl.Marker[]>([]);
  const poiElementsRef = useRef<Map<string, HTMLButtonElement>>(new Map());
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const popupModeRef = useRef<"hover" | "click" | null>(null);
  const visibleCategoriesRef = useRef(visibleCategories);
  const selectRef = useRef(onFeatureSelect);
  const mapPointSelectRef = useRef(onMapPointSelect);

  useEffect(() => {
    visibleCategoriesRef.current = visibleCategories;
  }, [visibleCategories]);

  useEffect(() => {
    selectRef.current = onFeatureSelect;
  }, [onFeatureSelect]);

  useEffect(() => {
    mapPointSelectRef.current = onMapPointSelect;
  }, [onMapPointSelect]);

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
              "circle-opacity": 0,
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
    map.on("click", (event) => {
      if (mapPointSelectRef.current === undefined) return;
      const renderedFeatures = map.isStyleLoaded()
        ? map.queryRenderedFeatures(event.point, {
            layers: ["urban-points", "urban-lines"],
          })
        : [];
      if (renderedFeatures.length > 0) return;
      mapPointSelectRef.current({
        latitude: event.lngLat.lat,
        longitude: event.lngLat.lng,
      });
    });
    map.on("mouseenter", "urban-points", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseenter", "urban-lines", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "urban-points", () => { map.getCanvas().style.cursor = ""; });
    map.on("mouseleave", "urban-lines", () => { map.getCanvas().style.cursor = ""; });
    mapRef.current = map;
    return () => {
      popupRef.current?.remove();
      popupRef.current = null;
      popupModeRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, [latitude, longitude]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const sourceDataCleanup = scheduleFeatureSourceData(map, SOURCE_ID, featureCollection(features));
    markerRef.current?.remove();
    popupRef.current?.remove();
    popupRef.current = null;
    popupModeRef.current = null;
    const element = document.createElement("div");
    element.className = "size-5 rounded-full border-2 border-primary-foreground bg-primary shadow-md";
    element.style.zIndex = "20";
    element.setAttribute(
      "aria-label",
      isPointInspection ? "Punto seleccionado en el mapa" : "Listing seleccionado",
    );
    markerRef.current = new maplibregl.Marker({ element }).setLngLat([longitude, latitude]).addTo(map);
    map.setCenter([longitude, latitude]);

    const poiElements = new Map<string, HTMLButtonElement>();
    const featureById = new Map(features.map((feature) => [feature.id, feature]));
    const openPopup = (
      feature: GeoFeature,
      poiLongitude: number,
      poiLatitude: number,
      mode: "hover" | "click",
    ) => {
      popupRef.current?.remove();
      const popup = new maplibregl.Popup({
        closeButton: mode === "click",
        closeOnClick: false,
        offset: 12,
        maxWidth: "260px",
      })
        .setLngLat([poiLongitude, poiLatitude])
        .setDOMContent(popupContent(feature));
      popupModeRef.current = mode;
      popupRef.current = popup;
      popup.on("close", () => {
        if (popupRef.current === popup) {
          popupRef.current = null;
          popupModeRef.current = null;
        }
      });
      popup.addTo(map);
      popup.getElement()?.style.setProperty("z-index", "30");
    };
    const closeHoverPopup = () => {
      if (popupModeRef.current !== "hover") return;
      popupRef.current?.remove();
      popupRef.current = null;
      popupModeRef.current = null;
    };

    poiMarkersRef.current = poiMarkerData(features, visibleCategoriesRef.current).flatMap(({ featureId, longitude: poiLongitude, latitude: poiLatitude, color }) => {
      const feature = featureById.get(featureId);
      if (!feature) return [];
      const poiElement = document.createElement("button");
      poiElement.type = "button";
      poiElement.className = "size-3 rounded-full border border-white p-0 shadow-sm";
      poiElement.style.backgroundColor = color;
      poiElement.style.zIndex = "10";
      poiElement.setAttribute("aria-label", `POI ${featureId}`);
      poiElement.addEventListener("mouseenter", () => {
        if (popupModeRef.current !== "click") {
          openPopup(feature, poiLongitude, poiLatitude, "hover");
        }
      });
      poiElement.addEventListener("mouseleave", closeHoverPopup);
      poiElement.addEventListener("click", () => {
        selectRef.current(featureId);
        openPopup(feature, poiLongitude, poiLatitude, "click");
      });
      poiElements.set(featureId, poiElement);
      return [new maplibregl.Marker({ element: poiElement })
        .setLngLat([poiLongitude, poiLatitude])
        .addTo(map)];
    });
    poiElementsRef.current = poiElements;

    return () => {
      sourceDataCleanup();
      popupRef.current?.remove();
      popupRef.current = null;
      popupModeRef.current = null;
      poiMarkersRef.current.forEach((poiMarker) => poiMarker.remove());
      poiMarkersRef.current = [];
      poiElementsRef.current.clear();
    };
  }, [features, isPointInspection, latitude, longitude, visibleCategoriesKey]);

  useEffect(() => {
    poiElementsRef.current.forEach((element, featureId) => {
      const isSelected = featureId === selectedFeatureId;
      element.classList.toggle("ring-2", isSelected);
      element.classList.toggle("ring-primary", isSelected);
    });
  }, [selectedFeatureId]);

  return <div ref={containerRef} className="min-h-80 w-full flex-1" aria-label="Mapa de contexto urbano" />;
}
