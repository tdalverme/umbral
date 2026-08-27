export function shouldReduceMotion() {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function viewportOptions(center: [number, number], zoom: number, reason: string) {
  const animated = !shouldReduceMotion();
  return { center, zoom, reason, animated, duration: animated ? 900 : 0 };
}
