"use client";

import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { MessageItem } from "@/components/chat/message-item";
import type { ChatMessageDto, ProposalDecision } from "@/lib/chat/types";

interface MessageListProps {
  messages: ChatMessageDto[];
  profileId: string;
  runId: string | null;
  pendingDecision: ProposalDecision | null;
  onDecision: (decision: Record<string, unknown>) => void;
  busy: boolean;
}

/** Scrollable message list with jump-to-latest (FR-027). */
export function MessageList({
  messages,
  profileId,
  runId,
  pendingDecision,
  onDecision,
  busy,
}: MessageListProps): React.ReactElement {
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    if (stickToBottom.current && scrollerRef.current) {
      scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <div className="flex h-full flex-col">
      <div
        ref={scrollerRef}
        className="min-h-0 flex-1 space-y-3 overflow-y-auto px-1 py-2"
        onScroll={(event) => {
          const target = event.currentTarget;
          stickToBottom.current =
            target.scrollHeight - target.scrollTop - target.clientHeight < 40;
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
              pendingDecision={pendingDecision}
              onDecision={onDecision}
              busy={busy}
            />
          ))
        )}
      </div>
      {messages.length > 0 && (
        <div className="flex justify-end">
          <Button
            className="h-7 px-2 text-xs"
            aria-label="Ir a lo más reciente"
            onClick={() => {
              stickToBottom.current = true;
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
