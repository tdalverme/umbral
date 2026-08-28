"use client";

import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type { MatchItem } from "@/lib/radar/client";
import type { RadarPoi } from "@/lib/radar/urban";
import { POI_CATEGORY_META } from "@/lib/radar/urban";
import { viewportOptions } from "@/lib/map/motion";
import { groupWithOffsets } from "./pin-offset";

const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const SOURCE_ID = "opportunities";

export function MapLuzSerena({
  matches,
  selectedId,
  hoverId,
  onSelect,
  pois = [],
  selectedPoiId = null,
  onPoiSelect,
}: Readonly<{
  matches: MatchItem[];
  selectedId: string | null;
  hoverId: string | null;
  onSelect: (id: string | null) => void;
  pois?: RadarPoi[];
  selectedPoiId?: string | null;
  onPoiSelect?: (id: string | null) => void;
}>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const points = matches
    .filter((m) => Array.isArray(m.geometry) && m.geometry.length === 2)
    .map((m) => ({ id: m.listing_id, lng: (m.geometry as [number, number])[0], lat: (m.geometry as [number, number])[1] }));

  const withOffsets = groupWithOffsets(points);
  const [debug, setDebug] = useState<string>("init");
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const markerElementsRef = useRef<Map<string, HTMLButtonElement>>(new Map());
  const poiMarkersRef = useRef<maplibregl.Marker[]>([]);
  const poiElementsRef = useRef<Map<string, HTMLButtonElement>>(new Map());
  const poiPopupRef = useRef<maplibregl.Popup | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: { type: "raster" as const, tiles: [TILE_URL], tileSize: 256, attribution: "© OpenStreetMap contributors" },
          [SOURCE_ID]: { type: "geojson" as const, data: { type: "FeatureCollection" as const, features: [] as never[] } },
        },
        layers: [
          { id: "background", type: "background" as const, paint: { "background-color": "#F4EFE6" } },
          { id: "osm", type: "raster" as const, source: "osm", paint: { "raster-opacity": 0.96 } },
          {
            id: "opportunity-points",
            type: "circle" as const,
            source: SOURCE_ID,
            paint: {
              "circle-color": "#293F38",
              "circle-radius": 9,
              "circle-opacity": 0,
              "circle-stroke-color": "#FFFAF2",
              "circle-stroke-width": 0,
            },
          },
        ],
      },
      center: [-58.3816, -34.6037],
      zoom: 12,
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    // exponer para debug en consola: window.__umbralMap
    (window as unknown as Record<string, unknown>).__umbralMap = map;
    (window as unknown as Record<string, unknown>).__umbralMapDebug = () => ({
      withOffsets,
      points,
      matches: matches.slice(0, 2),
      source: (() => { try { return (map.getSource("opportunities") as unknown as { _data?: unknown })?._data; } catch { return null; } })(),
      loaded: map.loaded(),
      styleLoaded: map.isStyleLoaded(),
      center: (() => { try { return map.getCenter(); } catch { return null; } })(),
      zoom: (() => { try { return map.getZoom(); } catch { return null; } })(),
      canvas: { w: map.getCanvas().width, h: map.getCanvas().height },
      layer: (() => { try { return map.getLayer("opportunity-points"); } catch { return null; } })(),
    });
    map.on("load", () => setDebug(`load: ${withOffsets.length} pts`));
    map.on("error", (e) => setDebug(`error: ${(e as unknown as { error?: { message?: string } })?.error?.message ?? "unknown"}`));
    mapRef.current = map;
    setDebug(`created: ${withOffsets.length} pts`);
    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      markerElementsRef.current.clear();
      poiMarkersRef.current.forEach((m) => m.remove());
      poiMarkersRef.current = [];
      poiElementsRef.current.clear();
      poiPopupRef.current?.remove();
      map.remove();
      mapRef.current = null;
      try {
        delete (window as unknown as Record<string, unknown>).__umbralMap;
      } catch {}
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
    const geojson = { type: "FeatureCollection" as const, features: features as never[] };
    // exponer debug actualizado
    (window as unknown as Record<string, unknown>).__umbralMapDebug = () => ({
      withOffsets,
      points,
      geojson,
      loaded: map.loaded(),
      styleLoaded: map.isStyleLoaded(),
      center: (() => { try { return map.getCenter(); } catch { return null; } })(),
      zoom: (() => { try { return map.getZoom(); } catch { return null; } })(),
      source: (() => { try { return (map.getSource("opportunities") as unknown as { _data?: unknown })?._data; } catch { return null; } })(),
    });

    let cancelled = false;
    const applyDataAndStyle = () => {
      if (cancelled || !mapRef.current) return;
      const source = map.getSource("opportunities") as maplibregl.GeoJSONSource | undefined;
      if (source) {
        source.setData(geojson);
      } else {
        // source aún no existe (style no cargado) — reintentar
        window.setTimeout(applyDataAndStyle, 100);
        return;
      }
      if (map.getLayer("opportunity-points")) {
        try {
          // Circle invisible — los markers visibles son HTML (como en playground geo-map-client)
          // Se mantiene el layer solo para hit-testing via queryRenderedFeatures
          map.setPaintProperty("opportunity-points", "circle-opacity", 0 as never);
          map.setPaintProperty("opportunity-points", "circle-stroke-opacity", 0 as never);
        } catch (e) {
          setDebug(`paint err ${(e as Error).message}`);
        }
        try {
          map.setLayoutProperty("opportunity-points", "visibility", "visible");
        } catch {}
      }
      if (selectedId) {
        const sel = withOffsets.find((p) => p.id === selectedId);
        if (sel) {
          const opts = viewportOptions([sel.lng, sel.lat], 16, "selección oportunidad");
          if (opts.animated) map.flyTo({ center: opts.center, zoom: opts.zoom, duration: opts.duration });
          else map.jumpTo({ center: opts.center, zoom: opts.zoom });
        }
        return;
      }
      if (withOffsets.length > 0) {
        const bounds = new maplibregl.LngLatBounds();
        withOffsets.forEach((p) => bounds.extend([p.lng, p.lat]));
        try {
          // padding moderado para no exceder canvas pequeño (antes left 400 causaba "cannot fit")
          map.fitBounds(bounds, {
            padding: 40,
            maxZoom: 14,
            duration: 700,
          });
        } catch {
          map.jumpTo({ center: [withOffsets[0].lng, withOffsets[0].lat], zoom: 13 });
        }
      }
    };

    // robusto: si ya está cargado aplica ya, si no espera load + polling
    if (map.isStyleLoaded()) {
      applyDataAndStyle();
    } else {
      map.once("load", applyDataAndStyle);
      map.once("styledata", applyDataAndStyle);
    }
    const t1 = window.setTimeout(applyDataAndStyle, 200);
    const t2 = window.setTimeout(applyDataAndStyle, 800);
    return () => {
      cancelled = true;
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [withOffsets, selectedId, hoverId]);

  // HTML markers visibles (como en playground geo-map-client) — no dependen de WebGL circle
  // Se crean solo cuando cambian los puntos, no en cada hover (el hover se maneja en el efecto siguiente sin recrear)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || withOffsets.length === 0) return;

    // limpiar previos
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    markerElementsRef.current.clear();

    const newMarkers: maplibregl.Marker[] = [];
    const elements = new Map<string, HTMLButtonElement>();

    withOffsets.forEach((p) => {
      const el = document.createElement("button");
      el.type = "button";
      el.setAttribute("aria-label", `Oportunidad ${p.id}`);
      // Importante: no usar transform en el elemento root del Marker (MapLibre lo usa para posicionar)
      // El scale se aplica vía width/height, no vía transform
      el.className =
        "rounded-full border-2 border-white shadow-md transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
      el.style.backgroundColor = p.id === selectedId ? "#DE6D4A" : "#293F38";
      el.style.width = p.id === selectedId ? "16px" : "14px";
      el.style.height = p.id === selectedId ? "16px" : "14px";
      el.style.zIndex = p.id === selectedId ? "20" : "10";
      el.addEventListener("click", () => onSelect(p.id));
      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([p.lng + p.offset.x, p.lat + p.offset.y])
        .addTo(map);
      newMarkers.push(marker);
      elements.set(p.id, el);
    });

    markersRef.current = newMarkers;
    markerElementsRef.current = elements;

    return () => {
      newMarkers.forEach((m) => m.remove());
      if (markersRef.current === newMarkers) {
        markersRef.current = [];
        markerElementsRef.current.clear();
      }
    };
  }, [withOffsets, onSelect]);

  // Actualizar estilo de markers existentes al cambiar selección/hover sin recrear ni tocar transform
  useEffect(() => {
    markerElementsRef.current.forEach((el, id) => {
      const isSelected = id === selectedId;
      const isHover = id === hoverId;
      el.style.backgroundColor = isSelected ? "#DE6D4A" : "#293F38";
      // solo width/height, nunca transform (MapLibre usa transform para posicionar)
      el.style.width = isSelected ? "16px" : isHover ? "15px" : "14px";
      el.style.height = isSelected ? "16px" : isHover ? "15px" : "14px";
      el.style.zIndex = isSelected ? "12" : isHover ? "11" : "10";
      el.classList.toggle("ring-2", isSelected);
      el.classList.toggle("ring-[var(--brand-terracotta)]", isSelected);
      // hover sutil sin scale: borde un poco más claro
      el.style.borderColor = isHover && !isSelected ? "#D9C59F" : "white";
    });
  }, [selectedId, hoverId]);

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

  // POI markers — estilo Luz serena, chicos, color por categoría, solo cuando hay pois filtrados
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // limpiar previos
    poiMarkersRef.current.forEach((m) => m.remove());
    poiMarkersRef.current = [];
    poiElementsRef.current.clear();
    poiPopupRef.current?.remove();
    poiPopupRef.current = null;

    if (pois.length === 0) return;

    const newMarkers: maplibregl.Marker[] = [];
    const elements = new Map<string, HTMLButtonElement>();

    pois.forEach((poi) => {
      const meta = POI_CATEGORY_META[poi.category as keyof typeof POI_CATEGORY_META];
      const color = meta?.color ?? "#4A6B5E";
      const isSelected = poi.id === selectedPoiId;

      const el = document.createElement("button");
      el.type = "button";
      el.setAttribute("aria-label", `${poi.name} — ${poi.category} a ${poi.distance_m} m`);
      el.className =
        "flex items-center justify-center rounded-full border shadow-sm transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
      el.style.backgroundColor = isSelected ? "#293F38" : color;
      el.style.borderColor = "white";
      el.style.borderWidth = "1.5px";
      el.style.width = isSelected ? "14px" : "10px";
      el.style.height = isSelected ? "14px" : "10px";
      el.style.zIndex = isSelected ? "15" : "9";
      el.style.opacity = isSelected ? "1" : "0.92";

      const showPopup = () => {
        poiPopupRef.current?.remove();
        const popup = new maplibregl.Popup({
          closeButton: false,
          closeOnClick: false,
          offset: 12,
          maxWidth: "220px",
          className: "umbral-poi-popup",
        })
          .setLngLat(poi.geometry)
          .setHTML(
            `<div style="font-family:var(--font-sans);font-size:12px;line-height:1.4;color:var(--foreground)"><div style="font-weight:600">${poi.name}</div><div style="color:var(--muted-foreground)">${meta?.label ?? poi.category} · ${poi.distance_m} m</div></div>`,
          )
          .addTo(map);
        poiPopupRef.current = popup;
      };
      const hidePopup = () => {
        // solo cerrar si no es selección fija
        if (selectedPoiId !== poi.id) {
          poiPopupRef.current?.remove();
          if (poiPopupRef.current?.isOpen() === false) poiPopupRef.current = null;
        }
      };

      el.addEventListener("mouseenter", showPopup);
      el.addEventListener("mouseleave", hidePopup);
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        onPoiSelect?.(poi.id);
        showPopup();
      });

      const marker = new maplibregl.Marker({ element: el, anchor: "center" }).setLngLat(poi.geometry).addTo(map);
      newMarkers.push(marker);
      elements.set(poi.id, el);
    });

    poiMarkersRef.current = newMarkers;
    poiElementsRef.current = elements;

    return () => {
      newMarkers.forEach((m) => m.remove());
      poiPopupRef.current?.remove();
      if (poiMarkersRef.current === newMarkers) {
        poiMarkersRef.current = [];
        poiElementsRef.current.clear();
      }
    };
  }, [pois, selectedPoiId, onPoiSelect]);

  // Actualizar estilo POI seleccionado sin recrear
  useEffect(() => {
    poiElementsRef.current.forEach((el, id) => {
      const isSelected = id === selectedPoiId;
      const poi = pois.find((p) => p.id === id);
      const meta = poi ? POI_CATEGORY_META[poi.category as keyof typeof POI_CATEGORY_META] : null;
      const baseColor = meta?.color ?? "#4A6B5E";
      el.style.backgroundColor = isSelected ? "#293F38" : baseColor;
      el.style.width = isSelected ? "14px" : "10px";
      el.style.height = isSelected ? "14px" : "10px";
      el.style.zIndex = isSelected ? "15" : "9";
      el.style.borderColor = isSelected ? "#FFFAF2" : "white";
      el.style.boxShadow = isSelected ? "0 2px 8px rgba(41,63,56,0.22)" : "0 1px 4px rgba(0,0,0,0.12)";
    });
  }, [selectedPoiId, pois]);

  // Cerrar popup al deseleccionar
  useEffect(() => {
    if (!selectedPoiId) {
      poiPopupRef.current?.remove();
      poiPopupRef.current = null;
    }
  }, [selectedPoiId]);

  if (withOffsets.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center bg-[var(--brand-linen)] text-sm text-muted-foreground" aria-label="Mapa de oportunidades">
        Mapa listo — seleccioná una oportunidad para centrar.
      </div>
    );
  }

  return (
    <div className="relative flex flex-1 min-h-0" aria-label="Mapa de oportunidades" role="region">
      <div ref={containerRef} className="flex-1 min-h-0" />
      {/* debug quitado en prod — se verifica con window.__umbralMapDebug() */}
    </div>
  );
}
