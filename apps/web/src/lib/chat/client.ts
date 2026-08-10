import type {
  ChatMessageDto,
  ChatSessionDto,
  ChatStreamEvent,
  UpdateProposalDto,
} from "@/lib/chat/types";

async function parseJson(response: Response): Promise<unknown> {
  if (response.ok) return response.json();
  let problem: { code?: string } | null = null;
  try {
    problem = (await response.json()) as { code?: string } | null;
  } catch {
    problem = null;
  }
  throw new Error(problem?.code ?? `http.${response.status}`);
}

function getJson(path: string): Promise<unknown> {
  return fetch(path, { headers: { "X-Correlation-ID": crypto.randomUUID() } }).then(
    parseJson,
  );
}

function sendJson(path: string, body: unknown): Promise<unknown> {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Correlation-ID": crypto.randomUUID() },
    body: JSON.stringify(body),
  }).then(parseJson);
}

/** Parses a text/event-stream body into typed chat events (R-07). */
export function parseStream(
  body: ReadableStream<Uint8Array> | null,
): AsyncIterable<ChatStreamEvent> {
  const decoder = new TextDecoder();
  let buffer = "";
  const queue: ChatStreamEvent[] = [];

  const reader = (body ?? new ReadableStream<Uint8Array>()).getReader();

  function flushEvent(block: string): void {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7);
      else if (line.startsWith("data: ")) data.push(line.slice(6));
    }
    if (data.length === 0) return;
    try {
      queue.push({ event, data: JSON.parse(data.join("\n")) } as ChatStreamEvent);
    } catch {
      // malformed SSE frame: skip (0 partial state)
    }
  }

  async function pull(): Promise<boolean> {
    const { done, value } = await reader.read();
    if (done) return false;
    buffer += decoder.decode(value, { stream: true });
    let sep = buffer.indexOf("\n\n");
    while (sep !== -1) {
      flushEvent(buffer.slice(0, sep));
      buffer = buffer.slice(sep + 2);
      sep = buffer.indexOf("\n\n");
    }
    return true;
  }

  const iterator = {
    async next(): Promise<IteratorResult<ChatStreamEvent>> {
      for (;;) {
        if (queue.length > 0) {
          const item = queue.shift()!;
          return { done: false, value: item };
        }
        if (await pull()) continue;
        if (queue.length > 0) continue;
        return { done: true, value: undefined as never };
      }
    },
    async return(): Promise<IteratorResult<ChatStreamEvent>> {
      return { done: true, value: undefined as never };
    },
    async throw(): Promise<IteratorResult<ChatStreamEvent>> {
      return { done: true, value: undefined as never };
    },
    [Symbol.asyncIterator](): AsyncIterator<ChatStreamEvent> {
      return iterator as unknown as AsyncIterator<ChatStreamEvent>;
    },
  } as AsyncIterable<ChatStreamEvent>;
  return iterator;
}

export const chatApi = {
  createSession: async (searchProfileId: string): Promise<ChatSessionDto> =>
    (await sendJson("/api/radar/chat/sessions", { search_profile_id: searchProfileId })) as ChatSessionDto,
  listSessions: async (searchProfileId: string): Promise<{ items: ChatSessionDto[] }> =>
    (await getJson(`/api/radar/chat/sessions?search_profile_id=${encodeURIComponent(searchProfileId)}`)) as {
      items: ChatSessionDto[];
    },
  history: async (sessionId: string): Promise<{ items: ChatMessageDto[] }> =>
    (await getJson(`/api/radar/chat/sessions/${sessionId}/messages`)) as { items: ChatMessageDto[] },
  send: (
    sessionId: string,
    text: string,
    clientMessageId?: string,
    context?: { entity: string; id: string },
  ): Promise<Response> =>
    fetch(`/api/radar/chat/sessions/${sessionId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Correlation-ID": crypto.randomUUID() },
      body: JSON.stringify({
        text,
        ...(clientMessageId ? { client_message_id: clientMessageId } : {}),
        ...(context ? { context } : {}),
      }),
    }),
  resume: (sessionId: string): Promise<Response> =>
    fetch(`/api/radar/chat/sessions/${sessionId}/resume`, {
      method: "POST",
      headers: { "X-Correlation-ID": crypto.randomUUID() },
    }),
  decide: (
    sessionId: string,
    runId: string,
    decision: Record<string, unknown>,
  ): Promise<Response> =>
    fetch(`/api/radar/chat/sessions/${sessionId}/runs/${runId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Correlation-ID": crypto.randomUUID() },
      body: JSON.stringify(decision),
    }),
  updateProposals: async (profileId: string, state = "pending"): Promise<{ items: UpdateProposalDto[] }> =>
    (await getJson(
      `/api/radar/profiles/${profileId}/update-proposals?state=${encodeURIComponent(state)}`,
    )) as { items: UpdateProposalDto[] },
};
