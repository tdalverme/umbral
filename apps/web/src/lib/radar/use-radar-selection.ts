"use client";

import { useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export function useRadarSelection() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedId = searchParams.get("listingId");
  const filter = searchParams.get("filter") as "all" | "saved" | "dismissed" | null;

  const setSelectedId = useCallback(
    (id: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (id) params.set("listingId", id);
      else params.delete("listingId");
      router.replace(`?${params.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  const setFilter = useCallback(
    (next: "all" | "saved" | "dismissed") => {
      const params = new URLSearchParams(searchParams.toString());
      if (next === "all") params.delete("filter");
      else params.set("filter", next);
      router.replace(`?${params.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  return { selectedId, filter: filter ?? "all", setSelectedId, setFilter };
}
