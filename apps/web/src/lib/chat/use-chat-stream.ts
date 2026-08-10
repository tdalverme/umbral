"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { chatApi, parseStream } from "@/lib/chat/client";
import { emitChatFirstFragment, emitChatStreamError } from "@/lib/chat/telemetry";
import type {
  ChatMessageDto,
  ChatSessionDto,
  ChatStreamEvent,
  ProposalDecision,
  StreamStatus,
} from "@/lib/chat/types";

/** Owns the single chat panel of a radar (Q3): session resume/create, SSE
 * streaming with dedupe and reconnection (R-11/R-13). */
export function useChatStream(searchProfileId: string) {
  const [session, setSession] = useState<ChatSessionDto | null>(null);
  const [messages, setMessages] = useState<ChatMessageDto[]>([]);
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [pendingDecision, setPendingDecision] = useState<ProposalDecision | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const pendingRunIdRef = useRef<string | null>(null);
  const waitingRef = useRef(false);
  const sessionIdRef = useRef<string>("");
  const mounted = useRef(true);
  const sentAtRef = useRef<number | null>(null);
  const firstFragmentRef = useRef(false);

  const refreshHistory = useCallback(async (sessionId: string) => {
    try {
      const page = await chatApi.history(sessionId);
      if (mounted.current) setMessages(page.items);
    } catch {
      // history is best-effort during a stream
    }
  }, []);

  const applyEvent = useCallback(
    (event: ChatStreamEvent) => {
      const data = event.data as Record<string, unknown>;
      switch (event.event) {
        case "chat.run_started":
          setStatus("running");
          setRunId(String(data.run_id));
          pendingRunIdRef.current = String(data.run_id);
          break;
        case "chat.reply_fragment": {
          const currentRun = String(data.run_id);
          const delta = String(data.delta ?? "");
          if (!firstFragmentRef.current && sentAtRef.current !== null) {
            firstFragmentRef.current = true;
            emitChatFirstFragment(searchProfileId, Date.now() - sentAtRef.current);
          }
          setMessages((current) => {
            const last = current[current.length - 1];
            if (last && last.role === "assistant" && last.message_id === `draft-${currentRun}`) {
              const content = last.content as { kind: string; text: string; refs?: unknown[] };
              return [
                ...current.slice(0, -1),
                {
                  ...last,
                  content: { ...content, text: (content.text ?? "") + delta },
                } as ChatMessageDto,
              ];
            }
            return [
              ...current,
              {
                message_id: `draft-${currentRun}`,
                role: "assistant",
                content: { kind: "reply", text: delta, refs: [] },
                created_at: new Date().toISOString(),
              },
            ];
          });
          break;
        }
        case "chat.tool_activity":
          setStatus("running");
          break;
        case "chat.interrupt_waiting": {
          const interrupt = data.interrupt as ProposalDecision;
          waitingRef.current = true;
          setPendingDecision(interrupt);
          setStatus("waiting_decision");
          break;
        }
        case "chat.run_completed":
          setStatus("completed");
          setPendingDecision(null);
          waitingRef.current = false;
          pendingRunIdRef.current = null;
          setRunId(null);
          if (sessionIdRef.current) void refreshHistory(sessionIdRef.current);
          break;
        case "chat.run_failed":
          setStatus("failed");
          setError(String(data.error_code ?? "agent.failed"));
          break;
        case "chat.run_interrupted":
          setStatus("failed");
          break;
      }
    },
    [refreshHistory, searchProfileId],
  );

  const streamFrom = useCallback(
    async (responsePromise: Promise<Response>) => {
      waitingRef.current = false;
      if (mounted.current) {
        setError(null);
        setPendingDecision(null);
      }
      let response: Response;
      try {
        response = await responsePromise;
      } catch (reason) {
        if (mounted.current) {
          setError(reason instanceof Error ? reason.message : "chat.network_error");
          emitChatStreamError(searchProfileId, "chat.network_error");
          setStatus("failed");
        }
        return;
      }
      if (!response.ok || response.body === null) {
        let problem: { code?: string } | null = null;
        try {
          problem = (await response.json()) as { code?: string } | null;
        } catch {
          problem = null;
        }
        if (!mounted.current) return;
        if (problem?.code === "chat.decision_pending") {
          setStatus("waiting_decision");
        } else {
          setError(problem?.code ?? `http.${response.status}`);
          emitChatStreamError(searchProfileId, problem?.code ?? `http.${response.status}`);
          setStatus("failed");
        }
        return;
      }
      for await (const event of parseStream(response.body)) {
        applyEvent(event);
      }
      if (mounted.current && !waitingRef.current) setStatus("completed");
    },
    [applyEvent, searchProfileId],
  );

  useEffect(() => {
    mounted.current = true;
    let cancelled = false;
    (async () => {
      try {
        const { items } = await chatApi.listSessions(searchProfileId);
        const latest = items.find((item) => item.status === "active") ?? items[0];
        const active = latest ?? (await chatApi.createSession(searchProfileId));
        if (cancelled) return;
        sessionIdRef.current = active.session_id;
        setSession(active);
        await refreshHistory(active.session_id);
      } catch (reason) {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "chat.session_error");
          setStatus("failed");
        }
      }
    })();
    return () => {
      cancelled = true;
      mounted.current = false;
    };
  }, [searchProfileId, refreshHistory]);

  const send = useCallback(
    async (text: string, context?: { entity: string; id: string }) => {
      if (!session || status === "sending" || status === "running" || status === "waiting_decision") {
        return;
      }
      const trimmed = text.trim();
      if (!trimmed) return;
      setMessages((current) => [
        ...current,
        {
          message_id: `local-${Date.now()}`,
          role: "user",
          content: { kind: "text", text: trimmed },
          created_at: new Date().toISOString(),
        },
      ]);
      setStatus("sending");
      sentAtRef.current = Date.now();
      firstFragmentRef.current = false;
      await streamFrom(chatApi.send(session.session_id, trimmed, crypto.randomUUID(), context));
    },
    [session, status, streamFrom],
  );

  const decide = useCallback(
    async (decision: Record<string, unknown>) => {
      if (!session || !pendingRunIdRef.current) return;
      const runId = pendingRunIdRef.current;
      setStatus("running");
      setPendingDecision(null);
      await streamFrom(chatApi.decide(session.session_id, runId, decision));
    },
    [session, streamFrom],
  );

  const resume = useCallback(async () => {
    if (!session) return;
    setStatus("resuming");
    await streamFrom(chatApi.resume(session.session_id));
  }, [session, streamFrom]);

  const startNewConversation = useCallback(async () => {
    if (!searchProfileId) return;
    try {
      const created = await chatApi.createSession(searchProfileId);
      sessionIdRef.current = created.session_id;
      setSession(created);
      setMessages([]);
      setStatus("idle");
      setError(null);
      setPendingDecision(null);
      setRunId(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "chat.session_error");
    }
  }, [searchProfileId]);

  return {
    session,
    messages,
    status,
    error,
    pendingDecision,
    runId,
    send,
    decide,
    resume,
    startNewConversation,
  };
}
