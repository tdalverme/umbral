/** Client-emitted product events (impression, detail viewed, source opened). */

export async function emitProductEvent(
  eventType: string,
  payload: Record<string, string | number>,
): Promise<void> {
  try {
    await fetch("/api/radar/events", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Correlation-ID": crypto.randomUUID() },
      body: JSON.stringify({ event_type: eventType, payload }),
    });
  } catch {
    // Event delivery never blocks the radar surface.
  }
}

export function emitImpression(profileId: string, runId: string, listingId: string): void {
  void emitProductEvent("recommendation.impression.v1", {
    search_profile_id: profileId,
    run_id: runId,
    listing_id: listingId,
  });
}

export function emitDetailViewed(profileId: string, runId: string, listingId: string): void {
  void emitProductEvent("recommendation.detail_viewed.v1", {
    search_profile_id: profileId,
    run_id: runId,
    listing_id: listingId,
  });
}

export function emitSourceOpened(profileId: string, runId: string, listingId: string, sourceId: string): void {
  void emitProductEvent("listing.source_opened.v1", {
    search_profile_id: profileId,
    run_id: runId,
    listing_id: listingId,
    source_id: sourceId,
  });
}

export function emitExplanationViewed(profileId: string, runId: string, listingId: string, scoreVersion: string): void {
  void emitProductEvent("recommendation.explanation_viewed.v1", {
    search_profile_id: profileId,
    run_id: runId,
    listing_id: listingId,
    score_version: scoreVersion,
  });
}

export function emitComparisonViewed(profileId: string, runId: string, listingCount: number, scoreVersion: string): void {
  void emitProductEvent("recommendation.comparison_viewed.v1", {
    search_profile_id: profileId,
    run_id: runId,
    listing_count: listingCount,
    score_version: scoreVersion,
  });
}

export function emitShortlistViewed(profileId: string, itemCount: number): void {
  void emitProductEvent("feedback.shortlist_viewed.v1", {
    search_profile_id: profileId,
    item_count: itemCount,
  });
}

export function emitDismissedViewed(profileId: string, itemCount: number): void {
  void emitProductEvent("feedback.dismissed_viewed.v1", {
    search_profile_id: profileId,
    item_count: itemCount,
  });
}
