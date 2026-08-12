"use client";

import { useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Composer } from "@/components/chat/composer";
import { MessageList } from "@/components/chat/message-list";
import { StreamStatus } from "@/components/chat/stream-status";
import { useChatStream } from "@/lib/chat/use-chat-stream";

interface ChatPanelProps {
  profileId: string;
}

/** The single chat panel of the radar page (Q3): resumes the latest session
 * of the radar or creates one; "conversación nueva" from the same panel.
 * A `?chat_context=listing:<id>` param sends a contextual question (UM-H4-025). */
export function ChatPanel({ profileId }: ChatPanelProps): React.ReactElement {
  const chat = useChatStream(profileId);
  const searchParams = useSearchParams();
  const contextRef = useRef<string | null>(null);
  const lastListingRef = useRef<string | null>(null);
  const { session, messages, send } = chat;

  useEffect(() => {
    const raw = searchParams.get("chat_context");
    if (raw && contextRef.current === null) contextRef.current = raw;
  }, [searchParams]);

  useEffect(() => {
    const context = contextRef.current;
    if (!context || !session || messages.length > 0) return;
    if (context.startsWith("listing:")) {
      contextRef.current = null;
      const listingId = context.slice("listing:".length);
      lastListingRef.current = listingId;
      void send(`Contame sobre el listing ${listingId} en mi radar.`, {
        entity: "listing",
        id: listingId,
      });
    }
  }, [session, messages.length, send]);

  useEffect(() => {
    if (messages.length === 0) {
      lastListingRef.current = null;
      return;
    }
    const listingRefs = messages.flatMap((message) => {
      const content = message.content as {
        kind: string;
        refs?: { entity: string; id: string }[];
      };
      return Array.isArray(content?.refs)
        ? content.refs.filter((ref) => ref.entity === "listing")
        : [];
    });
    if (listingRefs.length > 0) {
      lastListingRef.current = listingRefs[listingRefs.length - 1].id;
    }
  }, [messages]);

  const handleSend = (text: string): void => {
    void chat.send(
      text,
      lastListingRef.current
        ? { entity: "listing", id: lastListingRef.current }
        : undefined,
    );
  };

  return (
    <Card data-testid="chat-panel">
      <CardHeader className="flex flex-row items-center justify-between gap-3 pb-2">
        <CardTitle className="text-base">Chat con Umbral</CardTitle>
        <Button className="h-7 px-2 text-xs" onClick={() => void chat.startNewConversation()}>
          Conversación nueva
        </Button>
      </CardHeader>
      <CardContent className="flex h-80 flex-col gap-2">
        {chat.error && (
          <Alert role="alert">
            Ocurrió un error ({chat.error}).{" "}
            <Button className="h-auto p-0 text-xs underline" onClick={() => void chat.resume()}>
              Reanudar
            </Button>
          </Alert>
        )}
        <StreamStatus status={chat.status} />
        <div className="min-h-0 flex-1">
          <MessageList
            messages={chat.messages}
            profileId={profileId}
            runId={chat.runId}
            pendingDecision={chat.pendingDecision}
            onDecision={(decision) => void chat.decide(decision)}
            busy={chat.status === "running" || chat.status === "resuming"}
          />
        </div>
        <Composer status={chat.status} onSend={handleSend} />
      </CardContent>
    </Card>
  );
}
