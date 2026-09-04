import { describe, expect, it } from "vitest";

import { parseStream } from "@/lib/chat/client";
import { isProposalDecision } from "@/lib/chat/use-chat-stream";
import type { ChatStreamEvent } from "@/lib/chat/types";

function toStream(payload: string): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(payload));
      controller.close();
    },
  });
}

async function collect(payload: string): Promise<ChatStreamEvent[]> {
  const events: ChatStreamEvent[] = [];
  for await (const event of parseStream(toStream(payload))) {
    events.push(event);
  }
  return events;
}

describe("chat stream parsing", () => {
  it("no trata una confirmación corta como una propuesta renderizable", () => {
    expect(
      isProposalDecision({
        type: "conversation_confirmation",
        pending_ref: "pending:p-1",
        act_id: "a1",
      }),
    ).toBe(false);
  });

  it("parsea eventos SSE tipados", async () => {
    const body = [
      "event: chat.run_started",
      "id: 0",
      'data: {"run_id":"r1","session_id":"s1"}',
      "",
      "",
      "event: chat.reply_fragment",
      "id: 1",
      'data: {"run_id":"r1","delta":"hola"}',
      "",
      "",
    ].join("\n");
    const events = await collect(body);
    expect(events).toHaveLength(2);
    expect(events[0].event).toBe("chat.run_started");
    expect(events[1].event).toBe("chat.reply_fragment");
    expect((events[1] as { data: { delta: string } }).data.delta).toBe("hola");
  });

  it("salta frames malformados sin romper el stream (0 partial state)", async () => {
    const body = [
      "event: chat.run_started",
      "id: 0",
      'data: {"run_id":"r1","session_id":"s1"}',
      "",
      "",
      "event: chat.run_completed",
      "id: 1",
      "data: {not-json",
      "",
      "",
    ].join("\n");
    const events = await collect(body);
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("chat.run_started");
  });

  it("procesa frames divididos entre chunks", async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("event: chat.run_started\nid: 0\n"));
        controller.enqueue(new TextEncoder().encode('data: {"run_id":"r1"}\n\n'));
        controller.close();
      },
    });
    const events: ChatStreamEvent[] = [];
    for await (const event of parseStream(stream)) {
      events.push(event);
    }
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("chat.run_started");
  });
});
