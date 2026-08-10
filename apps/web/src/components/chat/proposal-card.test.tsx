import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProposalCard } from "@/components/chat/proposal-card";
import type { ProposalDecision } from "@/lib/chat/types";

const DECISION: ProposalDecision = {
  type: "proposal_decision",
  proposal_id: "p-1",
  diff: { budget_max: 900 },
  impact: { fields_changed: ["budget_max"] },
  expires_at: "2026-08-11T00:00:00Z",
};

describe("ProposalCard", () => {
  it("muestra el diff y emite approve", () => {
    const onDecision = vi.fn();
    render(<ProposalCard decision={DECISION} onDecision={onDecision} busy={false} />);
    expect(screen.getByText(/cambio propuesto en tu radar/i)).toBeTruthy();
    expect(screen.getByText("900")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Aprobar" }));
    expect(onDecision).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "approve" }),
    );
  });

  it("emite reject con motivo", () => {
    const onDecision = vi.fn();
    render(<ProposalCard decision={DECISION} onDecision={onDecision} busy={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Rechazar" }));
    expect(onDecision).toHaveBeenCalledWith(expect.objectContaining({ kind: "reject" }));
  });

  it("permite editar el presupuesto y emite edit", () => {
    const onDecision = vi.fn();
    render(<ProposalCard decision={DECISION} onDecision={onDecision} busy={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    const input = screen.getByLabelText(/presupuesto máx/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "1100" } });
    fireEvent.click(screen.getByRole("button", { name: "Aplicar edición" }));
    expect(onDecision).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "edit", change: { budget_max: 1100 } }),
    );
  });
});
