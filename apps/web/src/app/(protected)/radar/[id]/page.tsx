"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { RadarMap, matchPoints } from "@/components/radar/map";
import { radarApi, type MatchItem, type SearchProfile } from "@/lib/radar/client";
import { emitImpression } from "@/lib/radar/events";
import { neighborhoodLabel } from "@/lib/radar/neighborhoods";

const PAGE_SIZE = 25;
const POLL_INTERVAL_MS = 3000;

export default function RadarViewPage(): React.ReactElement {
  const params = useParams<{ id: string }>();
  const profileId = params.id;

  const [profile, setProfile] = useState<SearchProfile | null>(null);
  const [items, setItems] = useState<MatchItem[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [runState, setRunState] = useState<string | null>(null);
  const [nextAfter, setNextAfter] = useState<number | null>(null);
  const [selectedListingId, setSelectedListingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const emittedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    radarApi
      .getProfile(profileId)
      .then((value) => {
        setProfile(value);
        setRunState(value.latest_run?.state ?? null);
        setRunId(value.latest_run?.run_id ?? null);
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "radar.error");
      });
  }, [profileId, reloadKey]);

  const loadMatches = useCallback(
    (run: string | null) => {
      radarApi
        .matches(profileId, run, PAGE_SIZE, null)
        .then((page) => {
          setItems(page.items);
          setRunId(page.run_id);
          setRunState(page.run_state);
          setNextAfter(page.next_after_position);
          setError(null);
          page.items.forEach((item) => {
            const key = `${page.run_id}:${item.listing_id}`;
            if (!emittedRef.current.has(key)) {
              emittedRef.current.add(key);
              emitImpression(profileId, page.run_id, item.listing_id);
            }
          });
        })
        .catch((reason: unknown) => {
          setError(reason instanceof Error ? reason.message : "radar.error");
        });
    },
    [profileId],
  );

  useEffect(() => {
    loadMatches(runId);
  }, [loadMatches, runId]);

  useEffect(() => {
    if (!runState || (runState !== "pending" && runState !== "running")) return;
    const interval = window.setInterval(() => {
      radarApi.getProfile(profileId).then((value) => {
        setProfile(value);
        const state = value.latest_run?.state ?? null;
        setRunState(state);
        if (state === "succeeded") {
          window.clearInterval(interval);
          loadMatches(value.latest_run?.run_id ?? null);
        }
      });
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [runState, profileId, loadMatches]);

  async function changeStatus(status: "paused" | "active" | "archived"): Promise<void> {
    if (!profile) return;
    setError(null);
    try {
      const updated = await radarApi.setStatus(profile.search_profile_id, profile.version, status);
      setProfile(updated);
      setRunState(updated.latest_run?.state ?? null);
      setRunId(updated.latest_run?.run_id ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "radar.error");
    }
  }

  async function loadMore(): Promise<void> {
    if (nextAfter === null || runId === null) return;
    try {
      const page = await radarApi.matches(profileId, runId, PAGE_SIZE, nextAfter);
      setItems((current) => [...current, ...page.items]);
      setNextAfter(page.next_after_position);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "radar.error");
    }
  }

  const loading = profile === null;

  if (loading) {
    return (
      <main className="mx-auto w-full max-w-5xl px-6 py-16" id="main-content">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Spinner /> Cargando radar…
        </div>
      </main>
    );
  }

  if (error && !profile) {
    return (
      <main className="mx-auto w-full max-w-5xl px-6 py-16" id="main-content">
        <Alert role="alert">
          No se pudo cargar el radar ({error}).{" "}
          <Link href="/radar" className="underline">
            Volver a mis radares
          </Link>
        </Alert>
      </main>
    );
  }

  if (!profile) {
    return (
      <main className="mx-auto w-full max-w-5xl px-6 py-16" id="main-content">
        <Alert role="alert">Radar no encontrado o sin acceso.</Alert>
      </main>
    );
  }

  const generating = runState === "pending" || runState === "running";

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-16" id="main-content">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-4xl font-semibold tracking-tight">{profile.name}</h1>
          <p className="text-muted-foreground">
            {profile.zones.map(neighborhoodLabel).join(", ")} · hasta ${profile.budget_max.toLocaleString("es-AR")} ·{" "}
            {profile.min_rooms || "sin"} ambientes
          </p>
        </div>
        <div className="flex gap-2">
          {profile.status === "active" && (
            <Button className="min-h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80" onClick={() => void changeStatus("paused")}>
              Pausar
            </Button>
          )}
          {profile.status === "paused" && (
            <Button className="min-h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80" onClick={() => void changeStatus("active")}>
              Reanudar
            </Button>
          )}
          {profile.status !== "archived" && (
            <Button className="min-h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80" onClick={() => void changeStatus("archived")}>
              Archivar
            </Button>
          )}
        </div>
      </div>

      {error && (
        <Alert role="alert">
          Ocurrió un error ({error}).{" "}
          <Button
            className="min-h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80"
            onClick={() => setReloadKey((current) => current + 1)}
          >
            Reintentar
          </Button>
        </Alert>
      )}

      {generating && (
        <div className="mb-4 flex items-center gap-2 text-muted-foreground" role="status">
          <Spinner /> Generando resultados…
        </div>
      )}

      {!generating && runState === "failed" && (
        <Alert role="alert">
          La última generación de resultados falló. Los resultados anteriores siguen disponibles.
        </Alert>
      )}

      {!generating && runState === "succeeded" && items.length === 0 && (
        <Card>
          <CardHeader>
            <CardTitle>No hay resultados todavía</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Ninguna publicación cumple tus requisitos por ahora. Podés ampliar el presupuesto o los barrios y volver a
              intentar.
            </p>
          </CardContent>
        </Card>
      )}

      {runState === "succeeded" && items.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
          <ul className="space-y-3">
            {items.map((item) => (
              <li key={item.item_id}>
                <Link
                  href={`/listings/${item.listing_id}?profile=${profileId}&run=${runId ?? ""}`}
                  onClick={() => setSelectedListingId(item.listing_id)}
                >
                  <Card className="transition-colors hover:border-ring" data-testid="match-card">
                    <CardContent className="flex items-center justify-between gap-4 py-4">
                      <div>
                        <p className="font-medium">
                          {item.neighborhood ?? "Barrio no declarado"} · $
                          {Number(item.total_cost ?? 0).toLocaleString("es-AR")}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {item.surface_m2 !== null ? `${item.surface_m2} m²` : "superficie no declarada"} ·{" "}
                          {item.rooms !== null ? `${item.rooms} ambientes` : "ambientes no declarados"} ·{" "}
                          {item.source_id ?? "fuente no declarada"}
                        </p>
                      </div>
                      <span className="rounded-md bg-muted px-2 py-1 text-sm font-medium">Score {item.score.toFixed(2)}</span>
                    </CardContent>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
          <div className="sticky top-4 h-[420px]">
            <RadarMap
              points={matchPoints(items)}
              selectedListingId={selectedListingId}
              onSelect={setSelectedListingId}
            />
            <p className="mt-2 text-xs text-muted-foreground">
              Solo se muestran puntos con precisión geográfica autorizada; el resto aparece solo en la lista.
            </p>
          </div>
        </div>
      )}

      {nextAfter !== null && (
        <div className="mt-6 flex justify-center">
          <Button className="bg-muted text-foreground hover:bg-muted/80" onClick={() => void loadMore()}>
            Cargar más
          </Button>
        </div>
      )}
    </main>
  );
}
