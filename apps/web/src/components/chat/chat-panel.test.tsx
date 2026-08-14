import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const decide = vi.fn().mockResolvedValue(true);

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/chat/use-chat-stream", () => ({
  useChatStream: () => ({
    session: { session_id: "s1" },
    messages: [],
    status: "waiting_decision",
    error: null,
    pendingDecision: {
      type: "proposal_decision",
      kind: "profile",
      proposal_id: "p1",
      diff: { zones: ["nunez"] },
      impact: {},
      expires_at: "2026-08-15T00:00:00Z",
    },
    runId: "r1",
    send: vi.fn(),
    decide,
    resume: vi.fn(),
    startNewConversation: vi.fn(),
  }),
}));

vi.mock("@/components/chat/message-list", () => ({
  MessageList: ({ onDecision }: { onDecision: (decision: Record<string, unknown>) => void }) => (
    <button onClick={() => onDecision({ kind: "approve" })}>Decidir</button>
  ),
}));

vi.mock("@/components/chat/composer", () => ({
  Composer: () => <div />,
}));

vi.mock("@/components/chat/stream-status", () => ({
  StreamStatus: () => <div />,
}));

import { ChatPanel } from "@/components/chat/chat-panel";

describe("ChatPanel", () => {
  it("notifica al radar cuando termina una decisión del chat", async () => {
    const onDecisionApplied = vi.fn();
    render(<ChatPanel profileId="profile-1" onDecisionApplied={onDecisionApplied} />);

    fireEvent.click(screen.getByRole("button", { name: "Decidir" }));

    await waitFor(() => expect(onDecisionApplied).toHaveBeenCalledTimes(1));
  });
});
