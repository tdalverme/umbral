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
    <div className="flex h-full flex-col">
      <div
        ref={scrollerRef}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto px-1 py-2"
        onScroll={(event) => {
          const target = event.currentTarget;
          const atBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 40;
          stickToBottom.current = atBottom;
          setShowJump(!atBottom && messages.length > 0);
        }}
      >
        {messages.length === 0 ? (
          <p className="text-center text-xs text-muted-foreground">
            Preguntame sobre tu radar: criterios, oportunidades, comparaciones o cambios.
          </p>
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
          <div className="flex justify-start" data-testid="pending-decision-message">
            <div className="max-w-[85%] rounded-lg bg-muted px-3 py-2 text-sm text-foreground">
              <ProposalCard
                decision={pendingDecision}
                onDecision={onDecision}
                busy={busy}
              />
            </div>
          </div>
        )}
      </div>
      {showJump && (
        <div className="flex justify-end">
          <Button
            className="h-7 px-2 text-xs"
            aria-label="Ir a lo más reciente"
            onClick={() => {
              stickToBottom.current = true;
              setShowJump(false);
              if (scrollerRef.current) scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
            }}
          >
            Ir a lo más reciente
          </Button>
        </div>
      )}
    </div>
  );
}
