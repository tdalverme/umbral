import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Composer } from "@/components/chat/composer";

describe("Composer", () => {
  it("envía con Enter y permite nueva línea con Shift+Enter", () => {
    const onSend = vi.fn();
    render(<Composer status="idle" onSend={onSend} />);
    const input = screen.getByLabelText(/escribile a umbral/i);
    fireEvent.change(input, { target: { value: "hola" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("hola");
    expect(input).toHaveValue("");
  });

  it("Shift+Enter inserta nueva línea sin enviar", () => {
    const onSend = vi.fn();
    render(<Composer status="idle" onSend={onSend} />);
    const input = screen.getByLabelText(/escribile a umbral/i);
    fireEvent.change(input, { target: { value: "línea uno" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("permite seguir escribiendo mientras espera una decisión", () => {
    render(<Composer status="waiting_decision" onSend={vi.fn()} />);
    expect(screen.getByLabelText(/escribile a umbral/i)).not.toBeDisabled();
    expect(screen.getByLabelText(/escribile a umbral/i)).toHaveAttribute("placeholder", "Escribile a Umbral…");
  });
});
