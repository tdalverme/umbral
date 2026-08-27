"use client";

import { ChatPanel } from "@/components/chat/chat-panel";

export function RadarChatPanel({ profileId }: Readonly<{ profileId: string }>) {
  return (
    <div className="flex h-full flex-col">
      <ChatPanel profileId={profileId} onDecisionApplied={() => {}} />
      <p className="px-4 py-2 text-[11px] text-muted-foreground">Tool update_map_viewport mueve el mapa sin mutar filtros hard.</p>
    </div>
  );
}
