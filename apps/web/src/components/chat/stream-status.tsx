"use client";

import { Spinner } from "@/components/ui/spinner";
import type { StreamStatus } from "@/lib/chat/types";

const LABELS: Record<StreamStatus, string> = {
  idle: "",
  sending: "Enviando…",
  running: "Generando respuesta…",
  waiting_decision: "Esperando tu confirmación",
  resuming: "Reanudando la conversación…",
  failed: "Falló la generación",
  completed: "",
};

/** Renders the streaming state with a live region (FR-026/FR-035). */
export function StreamStatus({ status }: { status: StreamStatus }): React.ReactElement | null {
  const label = LABELS[status];
  if (!label) return null;
  const isWaiting = status === "waiting_decision";
  const isBusy = status === "sending" || status === "running" || status === "resuming";
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs ${
        isWaiting
          ? "border-[color-mix(in_srgb,var(--brand-terracotta)_22%,var(--border))] bg-[color-mix(in_srgb,var(--brand-terracotta)_10%,var(--card))] text-foreground"
          : isBusy
            ? "border-border bg-muted/50 text-muted-foreground"
            : "border-transparent bg-destructive/10 text-destructive"
      }`}
    >
      {isBusy ? <Spinner aria-hidden="true" className="size-3.5" /> : null}
      {isWaiting ? (
        <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-[var(--brand-terracotta)]" />
      ) : null}
      <span className="font-medium leading-none">{label}</span>
      {isWaiting && <span className="hidden text-muted-foreground sm:inline">· revisá la propuesta abajo</span>}
    </div>
  );
}
