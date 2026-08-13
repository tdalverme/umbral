"use client";

import { MiniCard } from "@/components/chat/mini-card";
import { ProposalCard } from "@/components/chat/proposal-card";
import type { ChatMessageDto, ProposalDecision } from "@/lib/chat/types";

interface MessageItemProps {
  message: ChatMessageDto;
  profileId: string;
  runId: string | null;
  pendingDecision: ProposalDecision | null;
  onDecision: (decision: Record<string, unknown>) => void;
  busy: boolean;
  onFeedback?: (text: string) => void;
}

function RefList({
  refs,
  profileId,
  runId,
  onFeedback,
}: {
  refs: { entity: string; id: string }[];
  profileId: string;
  runId: string | null;
  onFeedback?: (text: string) => void;
}): React.ReactElement | null {
  const listings = refs.filter((ref) => ref.entity === "listing");
  const proposals = refs.filter((ref) => ref.entity === "proposal");
  if (listings.length === 0 && proposals.length === 0) return null;
  return (
    <div className="mt-2 flex flex-col gap-2">
      {listings.map((ref) => (
        <MiniCard
          key={`listing-${ref.id}`}
          listingId={ref.id}
          profileId={profileId}
          runId={runId}
          onFeedback={onFeedback}
        />
      ))}
      {proposals.map((ref) => (
        <span key={`proposal-${ref.id}`} className="text-xs text-muted-foreground">
          Propuesta #{ref.id.slice(0, 8)}
        </span>
      ))}
    </div>
  );
}

/** A single chat bubble per role; renders refs and the pending decision (FR-031). */
export function MessageItem({
  message,
  profileId,
  runId,
  pendingDecision,
  onDecision,
  busy,
  onFeedback,
}: MessageItemProps): React.ReactElement {
  const isUser = message.role === "user";
  const text = String(message.content?.text ?? "");
  const content = message.content as { kind: string; text: string; refs?: { entity: string; id: string }[] };
  const refs = Array.isArray(content.refs) ? (content.refs as { entity: string; id: string }[]) : [];
  const isDraft = message.message_id.startsWith("draft-");
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
          isUser ? "bg-foreground text-background" : "bg-muted text-foreground"
        }`}
      >
        <p aria-live={isDraft ? "polite" : "off"}>{text}</p>
        {!isUser && refs.length > 0 && (
          <RefList refs={refs} profileId={profileId} runId={runId} onFeedback={onFeedback} />
        )}
        {!isUser && pendingDecision && (
          <ProposalCard decision={pendingDecision} onDecision={onDecision} busy={busy} />
        )}
      </div>
    </div>
  );
}
