import { render, screen } from "@testing-library/react";
import { createElement } from "react";

import RootLayout from "./layout";
import Page from "./page";

describe("foundation page", () => {
  it("provides an es-AR document, a keyboard skip link, and one main landmark", () => {
    const { container } = render(createElement(RootLayout, null, createElement(Page)));

    expect(container.querySelector("html")).toHaveAttribute("lang", "es-AR");
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
