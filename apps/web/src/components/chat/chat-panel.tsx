"use client";

import { useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Composer } from "@/components/chat/composer";
import { MessageList } from "@/components/chat/message-list";
import { ProposalCard } from "@/components/chat/proposal-card";
import { StreamStatus } from "@/components/chat/stream-status";
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

  const handleDecision = (decision: Record<string, unknown>): void => {
    void chat.decide(decision).then((applied) => {
      if (applied) onDecisionApplied?.();
    });
  };

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

        {chat.pendingDecision && (
          <div
            className="shrink-0 border-t border-border bg-card px-3 py-3 shadow-[0_-8px_24px_rgba(41,63,56,0.08)]"
            data-testid="pending-decision-bar"
          >
            <ProposalCard
              decision={chat.pendingDecision}
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
