"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { MessageItem } from "@/components/chat/message-item";
import { ProposalCard } from "@/components/chat/proposal-card";
import type { ChatMessageDto, ProposalDecision } from "@/lib/chat/types";

interface MessageListProps {
  messages: ChatMessageDto[];
  profileId: string;
  runId: string | null;
  pendingDecision: ProposalDecision | null;
  onDecision: (decision: Record<string, unknown>) => void;
  busy: boolean;
  onFeedback?: (text: string) => void;
}

/** Scrollable message list with jump-to-latest (FR-027). */
export function MessageList({
  messages,
  profileId,
  runId,
  pendingDecision,
  onDecision,
  busy,
  onFeedback,
}: MessageListProps): React.ReactElement {
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const stickToBottom = useRef(true);
  const [showJump, setShowJump] = useState(false);

  useEffect(() => {
    if (stickToBottom.current && scrollerRef.current) {
      scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
      setShowJump(false);
    } else if (messages.length > 0) {
      setShowJump(true);
    }
  }, [messages, pendingDecision]);

  return (
    <div className="relative flex h-full flex-col">
      <div
        ref={scrollerRef}
        className="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-3 [scrollbar-width:thin] [scrollbar-color:var(--border)_transparent]"
        onScroll={(event) => {
          const target = event.currentTarget;
          const atBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 48;
          stickToBottom.current = atBottom;
          setShowJump(!atBottom && messages.length > 0);
        }}
      >
        {messages.length === 0 ? (
          <div className="flex min-h-[140px] flex-col items-center justify-center rounded-xl border border-dashed border-border/70 bg-muted/30 px-6 py-8 text-center">
            <p className="max-w-[28ch] text-sm leading-relaxed text-muted-foreground">
              Preguntame sobre tu radar: criterios, oportunidades, comparaciones o cambios.
            </p>
            <p className="mt-1.5 text-xs text-muted-foreground/80">
              Ej.: “Bajá el presupuesto a 1.5M” o “Compará estas dos”
            </p>
          </div>
        ) : (
          messages.map((message) => (
            <MessageItem
              key={message.message_id}
              message={message}
              profileId={profileId}
              runId={runId}
              onFeedback={onFeedback}
            />
          ))
        )}
        {pendingDecision && (
          <div className="pt-1" data-testid="pending-decision-message">
            <ProposalCard decision={pendingDecision} onDecision={onDecision} busy={busy} />
          </div>
        )}
      </div>
      {showJump && (
        <div className="pointer-events-none absolute inset-x-0 bottom-2 flex justify-center">
          <Button
            className="pointer-events-auto h-8 rounded-full border border-border bg-card px-3.5 text-xs font-medium shadow-md hover:bg-muted"
            aria-label="Ir a lo más reciente"
            onClick={() => {
              stickToBottom.current = true;
              setShowJump(false);
              if (scrollerRef.current) scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
            }}
          >
            Ir a lo más reciente ↓
          </Button>
        </div>
      )}
    </div>
  );
}
