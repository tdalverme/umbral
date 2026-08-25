import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { PlaygroundView } from "@/components/playground/playground-view";

vi.mock("@/components/playground/geo-map", () => ({
  GeoMap: ({ onMapPointSelect }: { onMapPointSelect?: (point: { latitude: number; longitude: number }) => void }) => (
    <button
      aria-label="Mapa de prueba"
      onClick={() => onMapPointSelect?.({ latitude: -34.59, longitude: -58.4 })}
      type="button"
    />
  ),
}));

const demoFixture = {
  id: "demo",
  profile: { name: "Demo" },
  listings: [{ id: "demo-listing", neighborhood: "Palermo" }],
};
const realFixture = {
  id: "real-snapshot-test",
  profile: { name: "Snapshot real" },
  listings: [{ id: "real-listing-001", neighborhood: "Belgrano" }],
};

describe("PlaygroundView real snapshot source", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the map before listing inspection and inspects any clicked point", async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/fixtures")) {
        return Promise.resolve({ ok: true, json: async () => ({ fixtures: [demoFixture] }) });
      }
      if (String(input).endsWith("/geo") && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            fixture_id: "demo",
            listing_id: "point:-34.590000,-58.400000",
            radius_m: 600,
            listing: { id: "point:-34.590000,-58.400000", latitude: -34.59, longitude: -58.4, selection: "map_point" },
            features: [],
            primitives: [],
            signals: [],
            contract_version: "urban-contract-v2",
            snapshot_id: "urban-snapshot-test",
            attribution: "© OpenStreetMap contributors",
            warnings: [],
          }),
        });
      }
      return Promise.resolve({ ok: false, text: async () => "not found" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<PlaygroundView />);
    fireEvent.click(await screen.findByRole("button", { name: "Geo Lab" }));

    fireEvent.click(await screen.findByRole("button", { name: "Mapa de prueba" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        "/api/playground/geo",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            fixture_id: "demo",
            latitude: -34.59,
            longitude: -58.4,
            radius_m: 600,
          }),
        }),
      );
    });
  });

  it("selects a real snapshot and sends its listing to geo inspection", async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/fixtures")) {
        return Promise.resolve({ ok: true, json: async () => ({ fixtures: [demoFixture, realFixture] }) });
      }
      if (String(input).endsWith("/geo") && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            fixture_id: "real-snapshot-test",
            listing_id: "real-listing-001",
            radius_m: 600,
            listing: realFixture.listings[0],
            features: [],
            primitives: [],
            signals: [],
            contract_version: "urban-contract-v2",
            snapshot_id: "urban-snapshot-test",
            attribution: "© OpenStreetMap contributors",
            warnings: [],
          }),
        });
      }
      return Promise.resolve({ ok: false, text: async () => "not found" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<PlaygroundView />);
    fireEvent.click(await screen.findByRole("button", { name: "Geo Lab" }));

    const source = await screen.findByLabelText("Fuente de datos");
    fireEvent.change(source, { target: { value: "real-snapshot-test" } });
    expect(await screen.findByRole("option", { name: /real-listing-001/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Inspeccionar" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/playground/geo",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            fixture_id: "real-snapshot-test",
            listing_id: "real-listing-001",
            radius_m: 600,
          }),
        }),
      );
    });
  });

  it("inspects an arbitrary map point with coordinates instead of a listing", async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/fixtures")) {
        return Promise.resolve({ ok: true, json: async () => ({ fixtures: [demoFixture] }) });
      }
      if (String(input).endsWith("/geo") && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            fixture_id: "demo",
            listing_id: "point:-34.590000,-58.400000",
            radius_m: 600,
            listing: { id: "point:-34.590000,-58.400000", latitude: -34.59, longitude: -58.4 },
            features: [],
            primitives: [],
            signals: [],
            contract_version: "urban-contract-v2",
            snapshot_id: "urban-snapshot-test",
            attribution: "© OpenStreetMap contributors",
            warnings: [],
          }),
        });
      }
      return Promise.resolve({ ok: false, text: async () => "not found" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<PlaygroundView />);
    fireEvent.click(await screen.findByRole("button", { name: "Geo Lab" }));
    fireEvent.click(await screen.findByRole("button", { name: "Inspeccionar" }));
    fireEvent.click(await screen.findByRole("button", { name: "Mapa de prueba" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        "/api/playground/geo",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            fixture_id: "demo",
            latitude: -34.59,
            longitude: -58.4,
            radius_m: 600,
          }),
        }),
      );
    });
  });
});
