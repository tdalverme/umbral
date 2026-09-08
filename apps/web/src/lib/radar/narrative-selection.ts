export function shouldResetNarrative(
  current: { listingId: string; runId: string } | null,
  nextListingId: string | null,
  nextRunId: string | undefined,
): boolean {
  return nextListingId === null
    || current?.listingId !== nextListingId
    || current.runId !== nextRunId;
}
