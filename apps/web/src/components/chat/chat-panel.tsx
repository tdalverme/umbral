"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Composer } from "@/components/chat/composer";
import { MessageList } from "@/components/chat/message-list";
import { ProposalCard } from "@/components/chat/proposal-card";
import { StreamStatus } from "@/components/chat/stream-status";
import { chatApi } from "@/lib/chat/client";
import type { ProposalDecision, UpdateProposalDto } from "@/lib/chat/types";
import { useChatStream } from "@/lib/chat/use-chat-stream";

interface ChatPanelProps {
  profileId: string;
  onDecisionApplied?: () => void;
}

/** The single chat panel of the radar page (Q3): resumes the latest session
 * of the radar or creates one; "conversación nueva" from the same panel.
 * A `?chat_context=listing:<id>` param sends a contextual question (UM-H4-025). */
export function ChatPanel({
  profileId,
  onDecisionApplied,
}: ChatPanelProps): React.ReactElement {
  const chat = useChatStream(profileId);
  const searchParams = useSearchParams();
  const contextRef = useRef<string | null>(null);
  const lastListingRef = useRef<string | null>(null);
  const { session, messages, send } = chat;

  useEffect(() => {
    const raw = searchParams.get("chat_context");
    if (raw && contextRef.current === null) contextRef.current = raw;
  }, [searchParams]);

  useEffect(() => {
    const context = contextRef.current;
    if (!context || !session || messages.length > 0) return;
    if (context.startsWith("listing:")) {
      contextRef.current = null;
      const listingId = context.slice("listing:".length);
      lastListingRef.current = listingId;
      void send(`Contame sobre el listing ${listingId} en mi radar.`, {
        entity: "listing",
        id: listingId,
      });
    }
  }, [session, messages.length, send]);

  useEffect(() => {
    if (messages.length === 0) {
      lastListingRef.current = null;
      return;
    }
    const listingRefs = messages.flatMap((message) => {
      const content = message.content as {
        kind: string;
        refs?: { entity: string; id: string }[];
      };
      return Array.isArray(content?.refs)
        ? content.refs.filter((ref) => ref.entity === "listing")
        : [];
    });
    if (listingRefs.length > 0) {
      lastListingRef.current = listingRefs[listingRefs.length - 1].id;
    }
  }, [messages]);

  const handleSend = (text: string): void => {
    void chat.send(
      text,
      lastListingRef.current
        ? { entity: "listing", id: lastListingRef.current }
        : undefined,
    );
  };

  const handleFeedback = (text: string): void => {
    void chat.send(text);
  };

  const [fallbackProposal, setFallbackProposal] = useState<UpdateProposalDto | null>(null);

  // Fallback: si el SSE no entregó el interrupt pero el backend tiene un pending
  // (ej. reconexión, decisión pendiente previa), mostramos el pending de updateProposals
  // para que nunca quede "Esperando confirmación" sin card.
  useEffect(() => {
    if (chat.pendingDecision) {
      setFallbackProposal(null);
      return;
    }
    if (chat.status !== "waiting_decision") {
      setFallbackProposal(null);
      return;
    }
    let cancelled = false;
    chatApi
      .updateProposals(profileId, "pending")
      .then((page) => {
        if (!cancelled) setFallbackProposal(page.items[0] ?? null);
      })
      .catch(() => {
        if (!cancelled) setFallbackProposal(null);
      });
    return () => {
      cancelled = true;
    };
  }, [chat.pendingDecision, chat.status, profileId]);

  const handleDecision = (decision: Record<string, unknown>): void => {
    // Si hay fallback (SSE interrumpido), decidir contra su run_id/sesión
    if (!chat.pendingDecision && fallbackProposal?.waiting_run_id) {
      void chatApi
        .decide(fallbackProposal.session_id, fallbackProposal.waiting_run_id, decision)
        .then(async (response) => {
          if (response.body) {
            const reader = response.body.getReader();
            // drenar stream para que el backend cierre el run
            for (;;) {
              const { done } = await reader.read();
              if (done) break;
            }
          }
          onDecisionApplied?.();
          setFallbackProposal(null);
        })
        .catch(() => {});
      return;
    }
    void chat.decide(decision).then((applied) => {
      if (applied) onDecisionApplied?.();
    });
  };

  const fallbackDecision: ProposalDecision | null = fallbackProposal
    ? {
        type: "proposal_decision",
        kind: "profile",
        proposal_id: fallbackProposal.proposal_id,
        diff: fallbackProposal.diff as Record<string, unknown>,
        impact: fallbackProposal.impact as Record<string, unknown>,
        expires_at: fallbackProposal.expires_at,
      }
    : null;

  const activeDecision = chat.pendingDecision ?? fallbackDecision;

  return (
    <div
      data-testid="chat-panel"
      className="flex h-full min-h-0 flex-col bg-card"
    >
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border bg-card px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold leading-none tracking-tight text-foreground">
            Chat con Umbral
          </h2>
          <p className="mt-1 text-xs leading-none text-muted-foreground">
            Tu radar entiende lenguaje natural
          </p>
        </div>
        <Button
          className="h-8 shrink-0 rounded-full border border-border bg-background px-3 text-xs font-medium text-foreground hover:bg-muted"
          onClick={() => void chat.startNewConversation()}
        >
          Conversación nueva
        </Button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        {chat.error && (
          <div className="px-3 pt-3">
            <Alert role="alert" className="flex items-center justify-between gap-3 py-2 text-xs">
              <span>Ocurrió un error ({chat.error}).</span>
              <Button
                className="h-7 shrink-0 rounded-full px-3 text-xs"
                onClick={() => void chat.resume()}
              >
                Reanudar
              </Button>
            </Alert>
          </div>
        )}

        {chat.status !== "idle" && chat.status !== "completed" && (
          <div className="px-3 pt-3">
            <StreamStatus status={chat.status} />
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-hidden">
          <MessageList
            messages={chat.messages}
            profileId={profileId}
            runId={chat.runId}
            pendingDecision={null}
            onDecision={handleDecision}
            busy={chat.status === "running" || chat.status === "resuming"}
            onFeedback={handleFeedback}
          />
        </div>

        {activeDecision && (
          <div
            className="shrink-0 border-t border-border bg-card px-3 py-3 shadow-[0_-8px_24px_rgba(41,63,56,0.08)]"
            data-testid="pending-decision-bar"
          >
            <ProposalCard
              decision={activeDecision}
              onDecision={handleDecision}
              busy={chat.status === "running" || chat.status === "resuming"}
            />
          </div>
        )}

        <Composer status={chat.status} onSend={handleSend} />
      </div>
    </div>
  );
}
