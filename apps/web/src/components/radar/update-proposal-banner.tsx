"use client";

import { useCallback, useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { chatApi } from "@/lib/chat/client";
import type { UpdateProposalDto } from "@/lib/chat/types";

interface UpdateProposalBannerProps {
  profileId: string;
  onDecision?: () => void;
}

/** Shows pending agent profile changes with the SAME decision surface as the
 * chat (FR-033, R-09). */
export function UpdateProposalBanner({
  profileId,
  onDecision,
}: UpdateProposalBannerProps): React.ReactElement | null {
  const [proposals, setProposals] = useState<UpdateProposalDto[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    chatApi
      .updateProposals(profileId, "pending")
      .then((page) => {
        setProposals(page.items);
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "chat.update_proposals_error");
      });
  }, [profileId]);

  useEffect(() => {
    load();
  }, [load]);

  if (proposals.length === 0 && !error) return null;
  const proposal = proposals[0];

  async function act(decision: Record<string, unknown>): Promise<void> {
    if (!proposal?.waiting_run_id) return;
    setBusy(true);
    try {
      const response = await chatApi.decide(proposal.session_id, proposal.waiting_run_id, decision);
      // Drain the stream to let the decision complete server-side.
      if (response.body) {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        for await (const _chunk of parseChunks(response.body)) {
          // consume
        }
      }
      onDecision?.();
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "chat.decision_error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Alert role="status" data-testid="update-proposal-banner">
      {proposal && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm">
            Tenés un cambio propuesto por el chat:{" "}
            <strong>{Object.keys(proposal.diff).join(", ")}</strong>. Podés aprobarlo,
            editarlo en el chat o descartarlo.
          </p>
          <div className="flex gap-2">
            <Button
              className="min-h-8 bg-foreground px-3 text-xs text-background hover:bg-foreground/90"
              disabled={busy || !proposal.waiting_run_id}
              onClick={() => void act({ kind: "approve", idempotency_key: `banner-${crypto.randomUUID()}` })}
            >
              Aprobar
            </Button>
            <Button
              className="min-h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80"
              disabled={busy || !proposal.waiting_run_id}
              onClick={() => void act({ kind: "reject", reason: "desde el radar", idempotency_key: `banner-${crypto.randomUUID()}` })}
            >
              Descartar
            </Button>
          </div>
        </div>
      )}
      {error && (
        <span className="text-xs text-destructive" role="alert">
          {error}
        </span>
      )}
    </Alert>
  );
}

async function* parseChunks(body: ReadableStream<Uint8Array>): AsyncGenerator<Uint8Array> {
  const reader = body.getReader();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    if (value) yield value;
  }
}
