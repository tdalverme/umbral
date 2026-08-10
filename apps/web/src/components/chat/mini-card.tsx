"use client";

import Link from "next/link";

import { Card } from "@/components/ui/card";

interface MiniCardProps {
  listingId: string;
  profileId: string;
  runId: string | null;
}

/** Persistent, navigable reference to a listing (FR-031): links to the radar detail. */
export function MiniCard({ listingId, profileId, runId }: MiniCardProps): React.ReactElement {
  const query = new URLSearchParams({ profile: profileId });
  if (runId) query.set("run", runId);
  return (
    <Card data-testid="mini-card" className="border-border/60 p-2">
      <p className="text-xs text-muted-foreground">Listing en tu radar</p>
      <Link
        href={`/listings/${listingId}?${query.toString()}`}
        className="text-sm font-medium underline-offset-4 hover:underline"
        aria-label={`Ver detalle del listing ${listingId.slice(0, 8)}`}
      >
        Ver detalle #{listingId.slice(0, 8)}
      </Link>
    </Card>
  );
}
