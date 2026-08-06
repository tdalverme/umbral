/** Closed CABA neighborhood list of the search profile contract v1. */

export const CABA_NEIGHBORHOODS: Array<{ value: string; label: string }> = [
  { value: "palermo", label: "Palermo" },
  { value: "recoleta", label: "Recoleta" },
  { value: "belgrano", label: "Belgrano" },
  { value: "caballito", label: "Caballito" },
  { value: "villa_crespo", label: "Villa Crespo" },
  { value: "almagro", label: "Almagro" },
  { value: "balvanera", label: "Balvanera" },
  { value: "san_nicolas", label: "San Nicolás" },
  { value: "retiro", label: "Retiro" },
  { value: "puerto_madero", label: "Puerto Madero" },
  { value: "villa_urquiza", label: "Villa Urquiza" },
  { value: "nunez", label: "Núñez" },
  { value: "colegiales", label: "Colegiales" },
  { value: "villa_devoto", label: "Villa Devoto" },
  { value: "flores", label: "Flores" },
];

export function neighborhoodLabel(value: string): string {
  return CABA_NEIGHBORHOODS.find((item) => item.value === value)?.label ?? value;
}
