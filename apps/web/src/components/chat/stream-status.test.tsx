import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StreamStatus } from "@/components/chat/stream-status";

describe("StreamStatus", () => {
  it("anuncia el estado con una live region", () => {
    render(<StreamStatus status="running" />);
    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region.textContent).toContain("Generando respuesta");
  });

  it("no renderiza nada en estado idle o completado", () => {
    const { container: idle } = render(<StreamStatus status="idle" />);
    expect(idle.textContent).toBe("");
    const { container: done } = render(<StreamStatus status="completed" />);
    expect(done.textContent).toBe("");
  });

  it("distingue la espera de confirmación", () => {
    render(<StreamStatus status="waiting_decision" />);
    expect(screen.getByRole("status").textContent).toContain("confirmación");
  });
});
