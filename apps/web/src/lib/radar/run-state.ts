import type { RunState } from "@/lib/radar/client";

export function isTerminalRunState(state: RunState | string | null): boolean {
  return state === "succeeded" || state === "failed";
}
