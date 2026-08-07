"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback } from "react";

import { Button } from "@/components/ui/button";
import { DecisionList } from "@/components/radar/decision-list";
import { emitDismissedViewed } from "@/lib/radar/events";

export default function DismissedPage(): React.ReactElement {
  const params = useParams<{ id: string }>();
  const profileId = params.id;
  const onViewed = useCallback(
    (count: number) => emitDismissedViewed(profileId, count),
    [profileId],
  );
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-16" id="main-content">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-semibold tracking-tight">Descartados</h1>
        <Link href={`/radar/${profileId}`}>
          <Button className="bg-muted text-foreground hover:bg-muted/80">Volver al radar</Button>
        </Link>
      </div>
      <DecisionList profileId={profileId} decisionState="dismiss" onViewed={onViewed} />
    </main>
  );
}
