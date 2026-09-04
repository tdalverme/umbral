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
  concept_key: "Preferencia",
  polarity: "Sentido",
  concept_value: "Valor",
};

const VALUE_LABELS: Record<string, string> = {
  positive: "Me gusta",
  negative: "No me gusta",
  luminosidad: "Luminosidad",
  balcon: "Balcón",
  estado_general: "Estado general",
  tipo_cocina: "Tipo de cocina",
};

function formatCurrency(value: unknown): string | null {
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) return null;
  return new Intl.NumberFormat("es-AR", {
    style: "currency",
    currency: "ARS",
    maximumFractionDigits: 0,
  }).format(num);
}

function formatZones(value: unknown): string | null {
  if (!Array.isArray(value)) return null;
  return value.map((zone) => String(zone).replaceAll("_", " ")).join(" · ");
}

function renderValue(key: string, value: unknown): string {
  if (
    key === "budget_max" ||
    key === "budget_min" ||
    key === "surface_min" ||
    key === "surface_max"
  ) {
    const formatted = formatCurrency(value);
    if (formatted) return formatted;
  }
  if (key === "zones") {
    const formatted = formatZones(value);
    if (formatted) return formatted;
  }
  if (Array.isArray(value)) return value.map((v) => String(v)).join(", ");
  const text = String(value ?? "");
  return VALUE_LABELS[text] ?? text;
}

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

  const isPreference = decision.kind === "preference";
  const diff = decision.diff ?? {};
  const isRemoval = diff.operation === "remove";
  const fields = Object.entries(diff).filter(([key]) => key in FIELD_LABELS);
  const impact = decision.impact as Record<string, unknown> | undefined;
  const affectedCount =
    typeof impact?.["affected_matches"] === "number" ? (impact["affected_matches"] as number) : null;

  return (
    <Card
      data-testid="proposal-card"
      className="border-border bg-card p-4 shadow-sm"
    >
      <div className="flex items-center gap-2.5">
        <span aria-hidden className="size-2 shrink-0 rounded-full bg-[var(--brand-terracotta)]" />
        <p className="text-sm font-semibold leading-none tracking-tight text-foreground">
          {isPreference
            ? isRemoval
              ? "Quitar preferencia de tu radar"
              : "Preferencia propuesta en tu radar"
            : "Cambio propuesto en tu radar"}
        </p>
      </div>
      <p className="ml-[18px] mt-1 text-xs leading-relaxed text-muted-foreground">
        Revisá el cambio antes de aplicarlo. Podés aprobar, rechazar o editar el valor.
      </p>

      {fields.length > 0 ? (
        <ul className="mt-3 space-y-1.5 rounded-lg border border-border/60 bg-muted/40 px-3 py-2.5">
          {fields.map(([key, value]) => (
            <li key={key} className="flex items-baseline justify-between gap-3 text-sm">
              <span className="shrink-0 text-xs text-muted-foreground">{FIELD_LABELS[key]}</span>
              <strong className="text-right text-sm font-semibold text-foreground">
                {renderValue(key, value)}
              </strong>
            </li>
          ))}
          {affectedCount !== null && (
            <li className="border-t border-border/50 pt-1.5 text-xs text-muted-foreground">
              Afectará aprox. <strong className="font-medium text-foreground">{affectedCount}</strong> oportunidades de tu radar.
            </li>
          )}
        </ul>
      ) : (
        <p className="mt-3 rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          Sin campos detallados.
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          className="min-h-9 bg-foreground px-4 text-sm font-medium text-background hover:bg-foreground/90 focus-visible:ring-foreground"
          disabled={busy}
          onClick={approve}
          aria-busy={busy}
        >
          Aprobar
        </Button>
        <Button
          className="min-h-9 border border-border bg-background px-4 text-sm font-medium text-foreground hover:bg-muted"
          disabled={busy}
          onClick={reject}
        >
          Rechazar
        </Button>
        {!isPreference && (
          <Button
            className="min-h-9 border border-border bg-background px-3.5 text-sm text-foreground hover:bg-muted"
            disabled={busy}
            aria-expanded={editing}
            aria-controls="proposal-edit-field"
            onClick={() => setEditing((current) => !current)}
          >
            {editing ? "Cancelar edición" : "Editar"}
          </Button>
        )}
      </div>

      {editing && (
        <div
          id="proposal-edit-field"
          className="mt-3 flex items-end gap-2 rounded-lg border border-border bg-muted/30 p-3"
        >
          <label className="flex-1 text-xs font-medium text-foreground">
            Presupuesto máx. (ARS)
            <input
              type="number"
              inputMode="numeric"
              placeholder="Ej. 1600000"
              value={changeText}
              aria-label="Presupuesto máx."
              className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onChange={(event) => setChangeText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && changeText.trim() !== "" && !busy) edit();
              }}
            />
          </label>
          <Button
            className="min-h-9 shrink-0 px-4 text-sm"
            disabled={busy || changeText.trim() === ""}
            onClick={edit}
          >
            Aplicar edición
          </Button>
        </div>
      )}
    </Card>
  );
}
