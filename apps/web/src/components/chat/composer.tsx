"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import type { StreamStatus } from "@/lib/chat/types";

interface ComposerProps {
  status: StreamStatus;
  onSend: (text: string) => void;
}

const BLOCKING: StreamStatus[] = ["sending", "running", "resuming", "waiting_decision"];

/** Chat composer: Enter sends, Shift+Enter adds a new line (FR-028). */
export function Composer({ status, onSend }: ComposerProps): React.ReactElement {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const disabled = BLOCKING.includes(status);

  function submit(): void {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  return (
    <div className="flex items-end gap-2">
      <textarea
        ref={inputRef}
        rows={2}
        value={value}
        disabled={disabled}
        aria-label="Escribile a Umbral"
        placeholder={disabled ? "La conversación está en curso…" : "Escribile a Umbral…"}
        className="min-h-10 w-full resize-y rounded border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            submit();
          }
        }}
      />
      <Button onClick={submit} disabled={disabled || value.trim() === ""}>
        Enviar
      </Button>
    </div>
  );
}
