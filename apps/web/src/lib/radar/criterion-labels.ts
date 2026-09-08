/** Human-facing labels for deterministic explanation data. */

const CRITERION_LABELS: Record<string, string> = {
  presupuesto: "presupuesto",
  ambientes: "ambientes",
  superficie: "superficie",
  ubicacion: "ubicación",
  balcon: "balcón",
  luminosidad: "luz natural",
  estado_general: "estado general",
  piso: "piso",
  tipo_cocina: "tipo de cocina",
  moderno: "estado actualizado",
  dormitorios: "dormitorios",
  banos: "baños",
  mascotas: "admite mascotas",
  amoblado: "amoblamiento",
  ascensor: "ascensor",
  cochera: "cochera",
  piscina: "piscina",
  proximidad_cafes: "cafés cerca",
  acceso_transporte: "buena conectividad",
  proximidad_parque: "espacios verdes cerca",
  proximidad_compras: "servicios cotidianos cerca",
  vida_nocturna: "actividad nocturna",
  zona_comercial: "actividad comercial",
  caminabilidad: "posibilidades de caminar por la zona",
  calma_residencial: "calma residencial",
  ruido_transito: "poco ruido de tránsito",
  ruido_tren: "poco ruido de tren",
  ruido_ambiental: "poco ruido",
  acceso_escuela: "escuelas cerca",
  acceso_deporte: "opciones para hacer deporte cerca",
  acceso_cultura: "propuestas culturales cerca",
  acceso_bici: "conectividad en bici",
  acceso_salud: "servicios de salud cerca",
  precio_m2: "valor por metro cuadrado",
  variacion_precio: "cambio de precio",
  orientacion: "orientación",
};

export function criterionLabel(key: string): string {
  return CRITERION_LABELS[key] ?? "este criterio";
}

export function caveatCopy(key: string, state: "match" | "mismatch" | "unknown"): string {
  const label = criterionLabel(key);
  if (key === "vida_nocturna" && state === "mismatch") {
    return "La actividad nocturna es un punto para revisar antes de decidir.";
  }
  if (state === "unknown") {
    return `No puedo confirmar ${label} todavía.`;
  }
  return `${label[0]?.toLocaleUpperCase("es-AR")}${label.slice(1)} es un punto para revisar antes de decidir.`;
}
