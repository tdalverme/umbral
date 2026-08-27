export function signalLabel(category: string) {
  return category.replaceAll("_", " ");
}

export function formatDistance(m: number | null) {
  if (m === null) return "sin dato";
  if (m < 1000) return `${Math.round(m)} m`;
  return `${(m / 1000).toFixed(1)} km`;
}

export function snapshotBadge(snapshot?: { date: string; sha256: string } | null) {
  if (!snapshot) return "sin snapshot — dato no versionado";
  return `${snapshot.date} · ${snapshot.sha256.slice(0, 8)}`;
}
