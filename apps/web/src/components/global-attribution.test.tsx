import { render, screen } from "@testing-library/react";
import { createElement } from "react";

import { GlobalAttribution, OSM_ATTRIBUTION } from "./global-attribution";

describe("OSM global attribution", () => {
  it("shows the OpenStreetMap attribution on the global surface", () => {
    render(createElement(GlobalAttribution));

    const link = screen.getByRole("link", { name: OSM_ATTRIBUTION });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "https://www.openstreetmap.org/copyright");
    expect(link).toHaveTextContent("© OpenStreetMap contributors");
  });
});
