import type { GeoFeature } from "@/lib/playground/types";

// Categorías alineadas al contrato urbano v2 (transporte/cafés/parques + escolar/salud/cultural/deporte)
// Se mantienen en snake_case para compatibilidad con snapshot; se humanizan en UI.
export const POI_CATEGORIES = [
  "transporte",
  "cafes",
  "educacion",
  "salud",
  "comercio",
  "cultura",
  "deporte",
  "parques",
] as const;

export type PoiCategory = (typeof POI_CATEGORIES)[number];

export interface RadarPoi {
  id: string;
  name: string;
  category: PoiCategory;
  distance_m: number;
  geometry: [number, number]; // [lng, lat]
}

export const POI_CATEGORY_META: Record<PoiCategory, { label: string; color: string; icon: string }> = {
  transporte: { label: "Transporte", color: "#4A6B5E", icon: "bus" },
  cafes: { label: "Cafés", color: "#8B6F4E", icon: "coffee" },
  educacion: { label: "Educación", color: "#5B7C99", icon: "graduation" },
  salud: { label: "Salud", color: "#C07A7A", icon: "medical" },
  comercio: { label: "Comercio", color: "#7A9B8E", icon: "cart" },
  cultura: { label: "Cultura", color: "#7E6B9B", icon: "theater" },
  deporte: { label: "Deporte", color: "#6B8E7A", icon: "dumbbell" },
  parques: { label: "Parques", color: "#7A9B6B", icon: "leaf" },
};

function toRad(d: number) {
  return (d * Math.PI) / 180;
}
function toDeg(r: number) {
  return (r * 180) / Math.PI;
}

function haversineDistanceM(a: [number, number], b: [number, number]): number {
  const R = 6371000;
  const dLat = toRad(b[1] - a[1]);
  const dLng = toRad(b[0] - a[0]);
  const lat1 = toRad(a[1]);
  const lat2 = toRad(b[1]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function offsetMeters(origin: [number, number], distanceM: number, bearingDeg: number): [number, number] {
  const R = 6371000;
  const d = distanceM / R;
  const br = toRad(bearingDeg);
  const lat1 = toRad(origin[1]);
  const lng1 = toRad(origin[0]);
  const lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(br));
  const lng2 =
    lng1 +
    Math.atan2(Math.sin(br) * Math.sin(d) * Math.cos(lat1), Math.cos(d) - Math.sin(lat1) * Math.sin(lat2));
  return [toDeg(lng2), toDeg(lat2)];
}

const POI_NAMES: Record<PoiCategory, string[]> = {
  transporte: ["Colectivo 29", "Subte D - Palermo", "Colectivo 152", "Tren San Martín", "Colectivo 39"],
  cafes: ["Bonafide", "Café Martínez", "Starbucks", "La Panera Rosa", "Tino Heladería"],
  educacion: ["Escuela N° 12", "Jardín Arco Iris", "Colegio Belgrano", "UBA - CBC", "Escuela Técnica"],
  salud: ["Hospital Fernández", "Farmacia Central", "Clínica Santa Rosa", "Centro de Salud", "Sanatorio Güemes"],
  comercio: ["Disco", "Carrefour Express", "Kiosco 24h", "Verdulería Don Pepe", "Librería Yenny"],
  cultura: ["Teatro Colón anexo", "Museo MALBA", "Centro Cultural", "Biblioteca Nacional", "Cine Village"],
  deporte: ["Gimnasio Megatlón", "Club Palermo", "Cancha de Padel", "Polideportivo", "CrossFit Box"],
  parques: ["Plaza Palermo", "Parque Centenario", "Plaza Armenia", "Jardín Botánico", "Reserva Lago"],
};

export function generateMockPoisForListing(
  listingId: string,
  origin: [number, number] | null,
  seed = 0,
): RadarPoi[] {
  if (!origin) return [];
  const pois: RadarPoi[] = [];
  // Semilla simple para estabilidad por listing
  let s = listingId.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0) + seed;
  const rnd = () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };

  for (const cat of POI_CATEGORIES) {
    const count = 2 + Math.floor(rnd() * 2); // 2-3 por categoría
    for (let i = 0; i < count; i++) {
      const distance = 80 + rnd() * 520; // 80-600m
      const bearing = rnd() * 360;
      const geom = offsetMeters(origin, distance, bearing);
      const names = POI_NAMES[cat];
      const name = names[Math.floor(rnd() * names.length)];
      const id = `${listingId}-${cat}-${i}`;
      const dist = Math.round(haversineDistanceM(origin, geom));
      pois.push({
        id,
        name: `${name}${i > 0 ? ` ${i + 1}` : ""}`,
        category: cat,
        distance_m: dist,
        geometry: geom,
      });
    }
  }
  return pois.sort((a, b) => a.distance_m - b.distance_m);
}

export function poisToGeoFeatures(pois: RadarPoi[]): GeoFeature[] {
  return pois.map((p) => ({
    id: p.id,
    name: p.name,
    category: p.category,
    kind: "poi",
    distance_m: p.distance_m,
    geometry: { type: "Point", coordinates: [...p.geometry] } as unknown as Record<string, unknown>,
  }));
}

export function formatDistance(m: number): string {
  if (m < 1000) return `${Math.round(m)} m`;
  return `${(m / 1000).toFixed(1)} km`;
}
