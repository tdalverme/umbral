export type Offset = { x: number; y: number };

export function spiralOffset(index: number, spacing = 12): Offset {
  if (index === 0) return { x: 0, y: 0 };
  const angle = index * 2.399963; // golden angle approx
  const radius = spacing * Math.sqrt(index);
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

export function groupWithOffsets(points: Array<{ id: string; lng: number; lat: number }>): Array<{ id: string; lng: number; lat: number; offset: Offset }> {
  // naive O(n2) collision <30px approx ~0.0003 deg at zoom 14 ~ 30px; simplified to lat/lng proximity
  const threshold = 0.00035;
  const clusters = new Map<string, number>();
  return points.map((p, i) => {
    let clusterIndex = 0;
    for (let j = 0; j < i; j++) {
      const prev = points[j];
      const dist = Math.hypot(p.lng - prev.lng, p.lat - prev.lat);
      if (dist < threshold) clusterIndex++;
    }
    clusters.set(p.id, clusterIndex);
    const offset = spiralOffset(clusterIndex);
    // convert offset px approx to lng/lat delta at zoom 14: 1px ~ 0.000006 deg
    const pxToDeg = 0.000007;
    return { ...p, offset: { x: offset.x * pxToDeg, y: offset.y * pxToDeg } };
  });
}
