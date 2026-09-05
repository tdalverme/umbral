import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const chatMocks = vi.hoisted(() => ({
  fallback: false,
  streamDecide: vi.fn().mockResolvedValue(true),
  fallbackDecide: vi.fn(),
  resume: vi.fn(),
  updateProposals: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/chat/client", () => ({
  chatApi: {
    decide: chatMocks.fallbackDecide,
    updateProposals: chatMocks.updateProposals,
  },
}));

vi.mock("@/lib/chat/use-chat-stream", () => ({
  useChatStream: () => ({
    session: { session_id: "s1" },
    messages: [],
    status: "waiting_decision",
    error: null,
    pendingDecision: chatMocks.fallback
      ? null
      : {
          type: "proposal_decision",
          kind: "profile",
          proposal_id: "p1",
          diff: { zones: ["nunez"] },
          impact: {},
          expires_at: "2026-08-15T00:00:00Z",
        },
    runId: "r1",
    send: vi.fn(),
    decide: chatMocks.streamDecide,
    resume: chatMocks.resume,
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
  it("no reanuda un run después de aprobar una propuesta fallback", async () => {
    chatMocks.fallback = true;
    chatMocks.updateProposals.mockResolvedValue({
      items: [
        {
          proposal_id: "p1",
          session_id: "s1",
          search_profile_id: "profile-1",
          state: "pending",
          diff: { zones: ["nunez"] },
          impact: {},
          expires_at: "2026-08-15T00:00:00Z",
          rejection_reason: null,
          rejection_note: null,
          superseded_by_proposal_id: null,
          waiting_run_id: "r1",
        },
      ],
    });
    chatMocks.fallbackDecide.mockResolvedValue({ body: null } as Response);
    const onDecisionApplied = vi.fn();

    render(<ChatPanel profileId="profile-1" onDecisionApplied={onDecisionApplied} />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Aprobar" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Aprobar" }));

    await waitFor(() => expect(onDecisionApplied).toHaveBeenCalledTimes(1));
    expect(chatMocks.fallbackDecide).toHaveBeenCalledWith("s1", "r1", expect.objectContaining({ kind: "approve" }));
    expect(chatMocks.resume).not.toHaveBeenCalled();
  });

  it("notifica al radar cuando termina una decisión del chat", async () => {
    chatMocks.fallback = false;
    const onDecisionApplied = vi.fn();
    render(<ChatPanel profileId="profile-1" onDecisionApplied={onDecisionApplied} />);

    fireEvent.click(screen.getByRole("button", { name: "Decidir" }));

    await waitFor(() => expect(onDecisionApplied).toHaveBeenCalledTimes(1));
  });
});
