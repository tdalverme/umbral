"use client";

import { Spinner } from "@/components/ui/spinner";
import type { StreamStatus } from "@/lib/chat/types";

const LABELS: Record<StreamStatus, string> = {
  idle: "",
  sending: "Enviando…",
  running: "Generando respuesta…",
  waiting_decision: "Esperando tu confirmación…",
  resuming: "Reanudando la conversación…",
  failed: "Falló la generación",
  completed: "",
};

/** Renders the streaming state with a live region (FR-026/FR-035). */
export function StreamStatus({ status }: { status: StreamStatus }): React.ReactElement | null {
  const label = LABELS[status];
  if (!label) return null;
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 text-xs text-muted-foreground">
      {status === "sending" || status === "running" || status === "resuming" ? (
        <Spinner aria-hidden="true" />
      ) : null}
      <span>{label}</span>
    </div>
  );
}
