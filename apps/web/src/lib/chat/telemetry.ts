/** Chat performance/error telemetry for UM-H6-017 budgets (FR-043, R-15). */

import { emitProductEvent } from "@/lib/radar/events";

/** Emits the first-fragment latency of a chat turn (safe fields only). */
export function emitChatFirstFragment(searchProfileId: string, latencyMs: number): void {
  void emitProductEvent("chat.first_fragment.v1", {
    search_profile_id: searchProfileId,
    latency_ms: latencyMs,
  });
}

/** Emits a chat stream error with its typed code (safe fields only). */
export function emitChatStreamError(searchProfileId: string, errorCode: string): void {
  void emitProductEvent("chat.stream_error.v1", {
    search_profile_id: searchProfileId,
    error_code: errorCode,
  });
}
