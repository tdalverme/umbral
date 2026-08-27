import { vi } from "vitest";

export class Map {
  constructor() {}
  isStyleLoaded = vi.fn(() => true);
  getLayer = vi.fn(() => ({ id: "urban-points" }));
  getSource = vi.fn(() => ({ setData: vi.fn() }));
  setPaintProperty = vi.fn();
  once = vi.fn((_: string, cb: () => void) => cb());
  on = vi.fn();
  off = vi.fn();
  addControl = vi.fn();
  setCenter = vi.fn();
  getCanvas = vi.fn(() => ({ style: {} }));
  queryRenderedFeatures = vi.fn(() => []);
  remove = vi.fn();
}

export class Marker {
  constructor() {}
  setLngLat = vi.fn().mockReturnThis();
  addTo = vi.fn().mockReturnThis();
  remove = vi.fn();
}

export class Popup {
  constructor() {}
  setLngLat = vi.fn().mockReturnThis();
  setDOMContent = vi.fn().mockReturnThis();
  addTo = vi.fn().mockReturnThis();
  remove = vi.fn();
  on = vi.fn();
  getElement = vi.fn(() => ({ style: { setProperty: vi.fn() } }));
}

export class NavigationControl {
  constructor(_opts?: unknown) {}
}
