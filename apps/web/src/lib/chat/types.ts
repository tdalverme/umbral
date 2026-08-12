/** Types of the chat streaming surface consumed by the web panel (H4.3). */

export interface ChatSessionDto {
  session_id: string;
  search_profile_id: string;
  status: "active" | "paused" | "archived";
}

export interface ChatMessageDto {
  message_id: string;
  role: "user" | "assistant";
  content: { kind: "text"; text: string } | { kind: "reply"; text: string; refs: ChatRef[] };
  created_at: string;
}

export interface ChatRef {
  entity: "listing" | "criterion" | "evidence_ref" | "proposal";
  id: string;
}

export interface ProposalDecision {
  type: "proposal_decision";
  kind?: "profile" | "preference";
  proposal_id: string;
  diff: Record<string, unknown>;
  impact: Record<string, unknown>;
  expires_at: string;
}

export type ChatStreamEvent =
  | { event: "chat.run_started"; data: { run_id: string; session_id: string } }
  | { event: "chat.reply_fragment"; data: { run_id: string; delta: string } }
  | { event: "chat.tool_activity"; data: { run_id: string; tool: string; status: string } }
  | { event: "chat.interrupt_waiting"; data: { run_id: string; interrupt: ProposalDecision } }
  | { event: "chat.run_completed"; data: { run_id: string; message_id: string } }
  | { event: "chat.run_failed"; data: { run_id: string; error_code: string } }
  | { event: "chat.run_interrupted"; data: { run_id: string } };

export type StreamStatus =
  | "idle"
  | "sending"
  | "running"
  | "waiting_decision"
  | "resuming"
  | "failed"
  | "completed";

export interface UpdateProposalDto {
  proposal_id: string;
  session_id: string;
  search_profile_id: string;
  state: string;
  diff: Record<string, unknown>;
  impact: Record<string, unknown>;
  expires_at: string;
  rejection_reason: string | null;
  rejection_note: string | null;
  superseded_by_proposal_id: string | null;
  waiting_run_id: string | null;
}
