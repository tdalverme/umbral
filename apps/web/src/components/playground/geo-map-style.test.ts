import { describe, expect, it, vi } from "vitest";
import type { Map } from "maplibre-gl";

import {
  scheduleCategoryPaint,
  scheduleFeatureSourceData,
  scheduleSelectedFeaturePaint,
} from "./geo-map-style";

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

describe("scheduleCategoryPaint", () => {
  it("waits for the style load before applying category colors", () => {
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

    scheduleCategoryPaint(map as unknown as Map, ["park", "cafe"]);

    expect(map.setPaintProperty).not.toHaveBeenCalled();

    styleLoaded = true;
    onLoad?.();

    expect(map.setPaintProperty).toHaveBeenCalledWith(
      "urban-points",
      "circle-color",
      ["match", ["get", "category"], "cafe", "#e05252", "park", "#e08a2e", "#64748b"],
    );
  });
});

describe("scheduleFeatureSourceData", () => {
  it("updates the GeoJSON source when its source data arrives", () => {
    let styleLoaded = false;
    let onSourceData: ((event: { sourceId: string; isSourceLoaded: boolean }) => void) | undefined;
    const setData = vi.fn();
    const data = { type: "FeatureCollection", features: [] };
    const map = {
      isStyleLoaded: () => styleLoaded,
      getSource: vi.fn(() => ({ setData })),
      on: vi.fn((_event: "sourcedata", listener: (event: { sourceId: string; isSourceLoaded: boolean }) => void) => {
        onSourceData = listener;
      }),
      off: vi.fn(),
    };

    scheduleFeatureSourceData(map as unknown as Map, "playground-urban-features", data);

    expect(setData).not.toHaveBeenCalled();

    styleLoaded = true;
    expect(map.on).toHaveBeenCalledWith("sourcedata", expect.any(Function));
    onSourceData?.({ sourceId: "playground-urban-features", isSourceLoaded: false });

    expect(setData).toHaveBeenCalledWith(data);
  });
});
