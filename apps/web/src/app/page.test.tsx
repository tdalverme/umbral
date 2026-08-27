import { render, screen } from "@testing-library/react";
import { createElement } from "react";

import RootLayout, { metadata } from "./layout";
import Page from "./page";

describe("foundation page", () => {
  it("exposes the Umbral brand metadata", () => {
    expect(metadata).toMatchObject({
      title: "Umbral",
      description: "Tu próximo lugar se acerca.",
      icons: { icon: "/brand/umbral-favicon.svg" },
    });
  });
  it("provides an es-AR document, a keyboard skip link, and one main landmark", () => {
    render(createElement(RootLayout, null, createElement(Page)));
    expect(document.documentElement).toHaveAttribute("lang", "es-AR");
    expect(screen.getByRole("link", { name: /saltar al contenido principal/i })).toHaveAttribute(
      "href",
      "#main-content",
    );
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  it("shows a minimal runtime status without product-domain UI", () => {
    render(createElement(Page));

    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /umbral/i })).toBeInTheDocument();
    expect(screen.getByText(/fundación del runtime/i)).toBeInTheDocument();
    expect(screen.queryByText(/propiedad|inmueble|listado/i)).not.toBeInTheDocument();
  });
});
