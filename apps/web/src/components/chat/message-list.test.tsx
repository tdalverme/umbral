import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MessageList } from "@/components/chat/message-list";

describe("MessageList", () => {
  it("renderiza los mensajes y el estado vacío", () => {
    render(
      <MessageList
        messages={[]}
        profileId="p1"
        runId={null}
        pendingDecision={null}
        onDecision={() => undefined}
        busy={false}
      />,
    );
    expect(screen.getByText(/preguntame sobre tu radar/i)).toBeTruthy();
  });

  it("muestra botones de usuario y respuesta del asistente", () => {
    render(
      <MessageList
        messages={[
          {
            message_id: "1",
            role: "user",
            content: { kind: "text", text: "hola" },
            created_at: "2026-08-10T00:00:00Z",
          },
          {
            message_id: "2",
            role: "assistant",
            content: { kind: "reply", text: "todo ok", refs: [] },
            created_at: "2026-08-10T00:00:01Z",
          },
        ]}
        profileId="p1"
        runId={null}
        pendingDecision={null}
        onDecision={() => undefined}
        busy={false}
      />,
    );
    expect(screen.getByText("hola")).toBeTruthy();
    expect(screen.getByText("todo ok")).toBeTruthy();
    expect(screen.getByRole("button", { name: /ir a lo más reciente/i })).toBeTruthy();
  });
});
