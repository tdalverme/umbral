import { describe, expect, it, vi } from "vitest";
import type { Map } from "maplibre-gl";

import { scheduleSelectedFeaturePaint } from "./geo-map-style";

describe("scheduleSelectedFeaturePaint", () => {
  it("waits for the style load before changing the urban point layer", () => {
    let styleLoaded = false;
    let onLoad: (() => void) | undefined;
    const map = {
      isStyleLoaded: () => styleLoaded,
      getLayer: vi.fn(() => ({ id: "urban-points" })),
      setPaintProperty: vi.fn(),
      once: vi.fn((_event: "load", listener: () => void) => {
        onLoad = listener;
      }),
      off: vi.fn(),
    };

    scheduleSelectedFeaturePaint(map as unknown as Map, "poi-1");

    expect(map.setPaintProperty).not.toHaveBeenCalled();

    styleLoaded = true;
    onLoad?.();

    expect(map.setPaintProperty).toHaveBeenCalledWith(
      "urban-points",
      "circle-radius",
      ["case", ["==", ["get", "id"], "poi-1"], 10, 7],
    );
  });
});
