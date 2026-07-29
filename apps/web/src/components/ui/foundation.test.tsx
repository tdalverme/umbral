import { render, screen } from "@testing-library/react";
import { createElement } from "react";

import { Alert, AlertDescription, AlertTitle } from "./alert";
import { Button } from "./button";
import { Card, CardContent, CardHeader, CardTitle } from "./card";
import { Field, FieldError, FieldLabel } from "./field";
import { Input } from "./input";
import { Skeleton } from "./skeleton";
import { Spinner } from "./spinner";

describe("foundation UI primitives", () => {
  it("uses semantic color tokens and a visible focus treatment for the primary button", () => {
    render(createElement(Button, null, "Guardar"));

    const button = screen.getByRole("button", { name: "Guardar" });
    expect(button).toHaveClass("bg-primary", "text-primary-foreground", "focus-visible:ring-ring");
  });

  it("keeps a disabled button unavailable to keyboard and pointer interaction", () => {
    render(createElement(Button, { disabled: true }, "Guardar"));

    expect(screen.getByRole("button", { name: "Guardar" })).toBeDisabled();
  });

  it("associates a field label and validation message with its input", () => {
    render(
      createElement(
        Field,
        { "data-invalid": true },
        createElement(FieldLabel, { htmlFor: "search-name" }, "Nombre de búsqueda"),
        createElement(Input, { "aria-invalid": "true", id: "search-name" }),
        createElement(FieldError, null, "Ingresá un nombre."),
      ),
    );

    expect(screen.getByLabelText("Nombre de búsqueda")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Ingresá un nombre.")).toHaveAttribute("role", "alert");
  });

  it("preserves a card heading as an accessible content structure", () => {
    render(
      createElement(
        Card,
        null,
        createElement(CardHeader, null, createElement(CardTitle, null, "Estado del entorno")),
        createElement(CardContent, null, "Listo para configurar."),
      ),
    );

    expect(screen.getByRole("heading", { name: "Estado del entorno" })).toBeInTheDocument();
    expect(screen.getByText("Listo para configurar.")).toBeInTheDocument();
  });

  it("announces alert content through the alert role", () => {
    render(
      createElement(
        Alert,
        null,
        createElement(AlertTitle, null, "Configuración incompleta"),
        createElement(AlertDescription, null, "Revisá las variables requeridas."),
      ),
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Configuración incompleta");
    expect(screen.getByRole("alert")).toHaveTextContent("Revisá las variables requeridas.");
  });

  it("marks a skeleton as decorative while work is pending", () => {
    render(createElement(Skeleton, { "aria-label": "Cargando estado" }));

    expect(screen.getByLabelText("Cargando estado")).toHaveAttribute("aria-hidden", "true");
  });

  it("exposes a named status for a loading spinner", () => {
    render(createElement(Spinner, { "aria-label": "Cargando estado" }));

    expect(screen.getByRole("status", { name: "Cargando estado" })).toBeInTheDocument();
  });
});
