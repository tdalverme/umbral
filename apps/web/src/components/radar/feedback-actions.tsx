"use client";

import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { radarApi, type FeedbackEventType } from "@/lib/radar/client";

const ACTION_LABEL: Record<string, string> = {
  save: "Guardar",
  dismiss: "Descartar",
  like: "Me gusta",
  dislike: "No me gusta",
  contacted: "Contacté",
};

const REASONS_BY_ACTION: Record<string, string[]> = {
  like: ["price_fits", "location_yes", "access_ok", "balcony_wanted", "other"],
  save: ["price_fits", "location_yes", "access_ok", "balcony_wanted", "other"],
  dislike: [
    "price_too_high",
    "expensas_high",
    "location_no",
    "rooms_wrong",
    "surface_wrong",
    "building_state",
    "lighting_bad",
    "other",
  ],
  dismiss: [
    "price_too_high",
    "expensas_high",
    "location_no",
    "rooms_wrong",
    "surface_wrong",
    "building_state",
    "lighting_bad",
    "other",
  ],
};

interface FeedbackActionsProps {
  profileId: string;
  listingId: string;
  runId?: string | null;
  initialDecisionState?: FeedbackEventType | null;
  onStateChange?: (state: FeedbackEventType | null) => void;
}

export function FeedbackActions({
  profileId,
  listingId,
  runId = null,
  initialDecisionState = null,
  onStateChange,
}: FeedbackActionsProps): React.ReactElement {
  const [decision, setDecision] = useState<FeedbackEventType | null>(initialDecisionState);
  const [reasons, setReasons] = useState<string[]>([]);
  const [picking, setPicking] = useState<FeedbackEventType | null>(null);
  const [pending, setPending] = useState<FeedbackEventType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [freeFeedback, setFreeFeedback] = useState("");
  const freeFeedbackEnabled = process.env.NEXT_PUBLIC_FEEDBACK_FREE_FEEDBACK_ENABLED === "true";

  const record = useCallback(
    async (action: FeedbackEventType) => {
      setPending(action);
      setError(null);
      try {
        const result = await radarApi.recordFeedback(profileId, {
          listing_id: listingId,
          run_id: runId,
          event_type: action,
          reason_keys: reasons,
          free_feedback: freeFeedbackEnabled && freeFeedback.trim() ? freeFeedback : null,
          idempotency_key: crypto.randomUUID(),
        });
        setDecision(result.decision_state);
        setPicking(null);
        setReasons([]);
        setFreeFeedback("");
        onStateChange?.(result.decision_state);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "feedback.error");
      } finally {
        setPending(null);
      }
    },
    [profileId, listingId, runId, reasons, freeFeedback, freeFeedbackEnabled, onStateChange],
  );

  function handleAction(action: FeedbackEventType): void {
    if (action === "contacted") {
      void record(action);
      return;
    }
    if (action === decision) {
      setPicking(null);
      return;
    }
    if (REASONS_BY_ACTION[action]) {
      setPicking(action);
      return;
    }
    void record(action);
  }

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="feedback-actions">
      {(["save", "dismiss", "like", "dislike", "contacted"] as FeedbackEventType[]).map((action) => (
        <Button
          key={action}
          type="button"
          className={`min-h-8 px-3 text-xs ${
            decision === action
              ? "bg-foreground text-background hover:bg-foreground/90"
              : "bg-muted text-foreground hover:bg-muted/80"
          }`}
          disabled={pending !== null}
          onClick={() => handleAction(action)}
        >
          {ACTION_LABEL[action]}
        </Button>
      ))}
      {picking !== null && (
        <label className="flex flex-wrap items-center gap-1 text-xs">
          <span className="sr-only">Razones de {ACTION_LABEL[picking]}</span>
          {REASONS_BY_ACTION[picking].map((key) => (
            <span key={key}>
              <input
                type="checkbox"
                className="peer sr-only"
                checked={reasons.includes(key)}
                onChange={() =>
                  setReasons((current) =>
                    current.includes(key) ? current.filter((item) => item !== key) : [...current, key],
                  )
                }
              />
              <span className="rounded border border-border px-2 py-1 peer-checked:bg-foreground peer-checked:text-background">
                {key.replace(/_/g, " ")}
              </span>
            </span>
          ))}
          <Button type="button" className="min-h-8 px-3 text-xs" disabled={pending !== null} onClick={() => void record(picking)}>
            Confirmar razón
          </Button>
          {freeFeedbackEnabled && (
            <>
              <input
                aria-label="Explicá tu opinión (opcional)"
                placeholder="Explicá tu opinión (opcional)"
                value={freeFeedback}
                onChange={(event) => setFreeFeedback(event.target.value)}
                className="min-w-48 rounded border border-border px-2 py-1"
              />
              <span className="text-xs text-muted-foreground">
                Este texto es un insumo cualitativo para mejorar el producto y no se usa para cambios automáticos.
              </span>
            </>
          )}
        </label>
      )}
      {error && (
        <span className="text-xs text-destructive" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
