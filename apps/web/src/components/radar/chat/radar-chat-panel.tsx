"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { ChatPanel } from "@/components/chat/chat-panel";
import { ProposalCard } from "@/components/chat/proposal-card";

function MockChatPanel() {
  const searchParams = useSearchParams();
  const forceProposalPreview =
    searchParams.get("chat_preview") === "proposal" ||
    process.env.NEXT_PUBLIC_MOCK_CHAT_PROPOSAL === "1";

  const mockProposal = {
    type: "proposal_decision" as const,
    kind: "profile" as const,
    proposal_id: "mock-proposal-1",
    diff: { budget_max: 1600000 },
    impact: { affected_matches: 8 },
    expires_at: new Date(Date.now() + 1000 * 60 * 30).toISOString(),
  };

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b border-border bg-card px-4 py-3">
        <h2 className="text-sm font-semibold leading-none tracking-tight text-foreground">
          Chat con Umbral
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">Tu radar entiende lenguaje natural</p>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto px-3 py-3">
          <div className="rounded-xl border border-border/60 bg-muted/30 p-4">
            <p className="text-sm font-medium leading-tight text-foreground">
              Copiloto para encontrar tu próximo lugar
            </p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Preguntá en lenguaje natural y te muestro el porqué.
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <span className="rounded-full border border-border bg-card px-3 py-1 text-xs text-foreground shadow-xs">
                Busco 2 amb en Palermo con balcón
              </span>
              <span className="rounded-full border border-border bg-card px-3 py-1 text-xs text-foreground shadow-xs">
                Cerca de subte D, hasta $650k
              </span>
              <span className="rounded-full border border-border bg-card px-3 py-1 text-xs text-foreground shadow-xs">
                Que acepte mascotas
              </span>
            </div>
          </div>
          <div className="mt-4 space-y-4">
            <div className="flex justify-end">
              <div className="max-w-[86%] rounded-2xl rounded-br-md bg-foreground px-3.5 py-2.5 text-sm leading-relaxed text-background shadow-sm">
                Baja el presupuesto a 1.500.000
              </div>
            </div>
            <div className="flex justify-start">
              <div className="max-w-[86%] rounded-2xl rounded-bl-md border border-border bg-card px-3.5 py-2.5 text-sm leading-relaxed text-foreground shadow-sm">
                He creado una propuesta para bajar el presupuesto máximo a $ 1.500.000. ¿Querés que la
                confirme?
              </div>
            </div>
            {!forceProposalPreview && (
              <div className="rounded-2xl rounded-bl-md border border-border bg-card px-3.5 py-2.5 shadow-sm">
                <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  Umbral
                </p>
                <p className="mt-1 text-sm leading-relaxed text-foreground">
                  Encontré 8 oportunidades que vale la pena mirar. Todas respetan tu presupuesto; 2 están
                  un poco más lejos del subte.
                </p>
              </div>
            )}
          </div>
        </div>

        {forceProposalPreview && (
          <div className="shrink-0 border-t border-border bg-card px-3 py-3 shadow-[0_-8px_24px_rgba(41,63,56,0.08)]">
            <ProposalCard decision={mockProposal} onDecision={() => {}} busy={false} />
          </div>
        )}

        <div className="shrink-0 border-t border-border/60 bg-card px-3 py-3">
          <div className="rounded-xl border border-input bg-background px-3.5 py-2.5 text-sm text-muted-foreground">
            Escribile a Umbral…
          </div>
          <p className="mt-2 px-1 text-xs text-muted-foreground">El mapa se mueve sin cambiar tus filtros.</p>
        </div>
      </div>
    </div>
  );
}

export function RadarChatPanel({ profileId }: Readonly<{ profileId: string }>) {
  const isMock = process.env.NEXT_PUBLIC_USE_MOCKS === "1";
  if (isMock) {
    return (
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center p-8 text-xs text-muted-foreground">
            Cargando chat…
          </div>
        }
      >
        <MockChatPanel />
      </Suspense>
    );
  }
  return (
    <div className="flex h-full flex-col bg-card">
      <div className="flex-1 overflow-hidden">
        <ChatPanel profileId={profileId} onDecisionApplied={() => {}} />
      </div>
      <p className="shrink-0 border-t border-border/50 bg-muted/20 px-4 py-2 text-xs leading-relaxed text-muted-foreground">
        El mapa se mueve sin cambiar filtros.
      </p>
    </div>
  );
}
