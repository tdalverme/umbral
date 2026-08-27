import { render, screen } from "@testing-library/react";

import { BrandLogo } from "./brand-logo";

describe("BrandLogo", () => {
  it("renders the horizontal color logo with an accessible name", () => {
    render(<BrandLogo />);
    expect(screen.getByRole("img", { name: "Umbral" })).toHaveAttribute(
      "src",
      expect.stringContaining("/brand/umbral-logo-horizontal-color.svg"),
    );
  });

  it("supports a light symbol for compact dark surfaces", () => {
    render(<BrandLogo layout="symbol" tone="light" />);
    expect(screen.getByRole("img", { name: "Umbral" })).toHaveAttribute(
      "src",
      expect.stringContaining("/brand/umbral-symbol-light.svg"),
    );
  });
});
