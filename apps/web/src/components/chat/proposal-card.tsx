"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { ProposalDecision } from "@/lib/chat/types";

interface ProposalCardProps {
  decision: ProposalDecision;
  onDecision: (decision: Record<string, unknown>) => void;
  busy: boolean;
}

const FIELD_LABELS: Record<string, string> = {
  budget_max: "Presupuesto máx.",
  budget_min: "Presupuesto mín.",
  zones: "Zonas",
  min_rooms: "Ambientes mín.",
  surface_min: "Superficie mín.",
  surface_max: "Superficie máx.",
  name: "Nombre",
};

/** Renders a pending profile change with approve/edit/reject controls (FR-032). */
export function ProposalCard({ decision, onDecision, busy }: ProposalCardProps): React.ReactElement {
  const [editing, setEditing] = useState(false);
  const [changeText, setChangeText] = useState("");

  function approve(): void {
    onDecision({ kind: "approve", idempotency_key: `decision-${crypto.randomUUID()}` });
  }

  function reject(): void {
    onDecision({ kind: "reject", idempotency_key: `decision-${crypto.randomUUID()}` });
  }

  function edit(): void {
    onDecision({
      kind: "edit",
      change: { budget_max: Number(changeText) || undefined },
      idempotency_key: `decision-${crypto.randomUUID()}`,
    });
    setEditing(false);
    setChangeText("");
  }

  const diff = decision.diff as Record<string, unknown>;
  const fields = Object.entries(diff).filter(([key]) => key in FIELD_LABELS);

  return (
    <Card data-testid="proposal-card" className="mt-2 border-border/60 p-3">
      <p className="text-xs font-medium">Cambio propuesto en tu radar</p>
      {fields.length > 0 ? (
        <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
          {fields.map(([key, value]) => (
            <li key={key}>
              {FIELD_LABELS[key]}: <strong className="text-foreground">{String(value)}</strong>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-xs text-muted-foreground">Sin campos detallados.</p>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        <Button className="min-h-8 bg-foreground px-3 text-xs text-background hover:bg-foreground/90" disabled={busy} onClick={approve}>
          Aprobar
        </Button>
        <Button className="min-h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80" disabled={busy} onClick={reject}>
          Rechazar
        </Button>
        <Button
          className="min-h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80"
          disabled={busy}
          onClick={() => setEditing((current) => !current)}
        >
          Editar
        </Button>
      </div>
      {editing && (
        <div className="mt-2 flex items-end gap-2">
          <label className="flex-1 text-xs text-muted-foreground">
            Presupuesto máx.
            <input
              type="number"
              inputMode="numeric"
              value={changeText}
              className="mt-1 w-full rounded border border-input bg-background px-2 py-1 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onChange={(event) => setChangeText(event.target.value)}
            />
          </label>
          <Button className="min-h-8 px-3 text-xs" disabled={busy || changeText.trim() === ""} onClick={edit}>
            Aplicar edición
          </Button>
        </div>
      )}
    </Card>
  );
}
