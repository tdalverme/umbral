"use client";

import { useCallback, useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { radarApi, type Proposal } from "@/lib/radar/client";

interface ProposalBannerProps {
  profileId: string;
  onDecision?: () => void;
}

function humanizeBannerError(code: string): string {
  if (code.startsWith("http.5")) return "No se pudo cargar propuestas — reintentá.";
  if (code.startsWith("http.4")) return "No se pudo cargar propuestas.";
  if (code.includes("Failed to fetch")) return "Sin conexión.";
  return code;
}

export function ProposalBanner({ profileId, onDecision }: ProposalBannerProps): React.ReactElement | null {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    radarApi
      .listProposals(profileId, "pending")
      .then((page) => {
        setProposals(page.items);
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "learning.error");
      });
  }, [profileId]);

  useEffect(() => {
    load();
  }, [load]);

  if (proposals.length === 0 && !error) return null;

  async function confirm(proposalId: string): Promise<void> {
    setBusy(true);
    try {
      await radarApi.confirmProposal(profileId, proposalId);
      onDecision?.();
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "learning.error");
    } finally {
      setBusy(false);
    }
  }

  async function reject(proposalId: string): Promise<void> {
    setBusy(true);
    try {
      await radarApi.rejectProposal(profileId, proposalId);
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "learning.error");
    } finally {
      setBusy(false);
    }
  }

  const proposal = proposals[0];
  return (
    <Alert role="status" data-testid="proposal-banner" className="py-2">
      {proposal && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm">
            El radar aprendió de tu feedback:{" "}
            <strong>
              {proposal.change.polarity === "negative" ? "bajar la importancia de" : "priorizar"}{" "}
              {proposal.change.concept_key.replace(/_/g, " ")}
            </strong>{" "}
            en esta búsqueda. Podés confirmarlo, ajustarlo o descartarlo.
          </p>
          <div className="flex gap-2">
            <Button
              className="min-h-9 bg-foreground px-3 py-2 text-xs text-background hover:bg-foreground/90"
              disabled={busy}
              onClick={() => void confirm(proposal.proposal_id)}
            >
              Confirmar
            </Button>
            <Button className="min-h-9 bg-muted px-3 py-2 text-xs text-foreground hover:bg-muted/80" disabled={busy} onClick={() => void reject(proposal.proposal_id)}>
              Descartar
            </Button>
          </div>
        </div>
      )}
      {error && (
        <span className="text-xs text-destructive" role="alert">
          {humanizeBannerError(error)}
        </span>
      )}
    </Alert>
  );
}
