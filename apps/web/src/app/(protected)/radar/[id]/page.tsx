"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { ChatPanel } from "@/components/chat/chat-panel";
import { RadarMap, matchPoints } from "@/components/radar/map";
import { FeedbackActions } from "@/components/radar/feedback-actions";
import { ProposalBanner } from "@/components/radar/proposal-banner";
import { UpdateProposalBanner } from "@/components/radar/update-proposal-banner";
import { RadarShell } from "@/components/radar/radar-shell";
import { radarApi, type Explanation, type FeedbackEventType, type MatchItem, type SearchProfile } from "@/lib/radar/client";
import { emitExplanationViewed, emitImpression } from "@/lib/radar/events";
import { neighborhoodLabel } from "@/lib/radar/neighborhoods";

const PAGE_SIZE = 25;
const POLL_INTERVAL_MS = 3000;
const LEGACY_SCORE_POLICY = "scoring-baseline-v1";
const EVIDENCE_LABEL: Record<string, string> = { strong: "fuerte", medium: "media", low: "baja" };

function humanizeError(code: string): string {
  if (code.startsWith("http.401") || code === "unauthorized") return "No autorizado — iniciá sesión de nuevo.";
  if (code.startsWith("http.403")) return "Sin permiso para este radar.";
  if (code.startsWith("http.404") || code === "radar.error") return "Radar no encontrado.";
  if (code.startsWith("http.429")) return "Demasiadas solicitudes — probá de nuevo en unos segundos.";
  if (code.startsWith("http.5")) return "Error del servidor — reintentá o contactá soporte si persiste.";
  if (code === "explanation_unavailable") return "Explicación no disponible para este run.";
  if (code === "network_error" || code.includes("Failed to fetch")) return "Sin conexión — revisá tu red y reintentá.";
  return code;
}

function EvidenceBadge({ level }: { level: "strong" | "medium" | "low" }): React.ReactElement {
  return (
    <span
      className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
      aria-label={`evidencia ${EVIDENCE_LABEL[level]}`}
    >
      evidencia {EVIDENCE_LABEL[level]}
    </span>
  );
}

function ReasonsStrip({ explanation }: { explanation: Explanation }): React.ReactElement {
  const top = explanation.reasons.slice(0, 3);
  if (top.length === 0 && explanation.missing_data.length === 0) return <span />;
  return (
    <ul className="mt-2 flex flex-wrap gap-1.5" aria-label="razones del match">
      {top.map((reason) => (
        <li key={reason.criterion_key} className="flex items-center gap-1">
          <span className="text-xs">{reason.text}</span>
          <EvidenceBadge level={reason.evidence_level} />
        </li>
      ))}
      {explanation.missing_data.length > 0 && (
        <li className="text-xs text-muted-foreground">
          sin datos: {explanation.missing_data.join(", ")}
        </li>
      )}
    </ul>
  );
}

export default function RadarViewPage(): React.ReactElement {
  const params = useParams<{ id: string }>();
  const profileId = params.id;
  const isMock = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

  const [profile, setProfile] = useState<SearchProfile | null>(null);
  const [allRadars, setAllRadars] = useState<SearchProfile[]>([]);
  const [items, setItems] = useState<MatchItem[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [runState, setRunState] = useState<string | null>(null);
  const [nextAfter, setNextAfter] = useState<number | null>(null);
  const [selectedListingId, setSelectedListingId] = useState<string | null>(null);
  const [explanations, setExplanations] = useState<Record<string, Explanation>>({});
  const [legacyRun, setLegacyRun] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [decisionStates, setDecisionStates] = useState<Record<string, FeedbackEventType | null>>({});
  const emittedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (isMock) {
      import("@/lib/radar/mock-shell-data").then(({ MOCK_PROFILES, MOCK_MATCHES }) => {
        const found = MOCK_PROFILES.find((p) => p.search_profile_id === profileId) ?? MOCK_PROFILES[0];
        setProfile(found);
        setAllRadars(MOCK_PROFILES);
        setRunState("succeeded");
        setRunId(found.latest_run?.run_id ?? "run-preview-1");
        setLegacyRun(false);
        setItems(MOCK_MATCHES);
        setNextAfter(null);
        setError(null);
      });
      return;
    }
    radarApi
      .getProfile(profileId)
      .then((value) => {
        setProfile(value);
        setRunState(value.latest_run?.state ?? null);
        setRunId(value.latest_run?.run_id ?? null);
        setLegacyRun(value.latest_run?.score_policy_version === LEGACY_SCORE_POLICY);
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "radar.error");
      });
    radarApi
      .listProfiles()
      .then((profiles) => setAllRadars(profiles))
      .catch(() => {});
  }, [profileId, reloadKey, isMock]);

  const loadExplanations = useCallback(
    (run: string) => {
      radarApi
        .explanations(profileId, run, PAGE_SIZE, null)
        .then((page) => {
          const byListing: Record<string, Explanation> = {};
          for (const item of page.items) byListing[item.listing_id] = item;
          setExplanations(byListing);
          setError(null);
        })
        .catch((reason: unknown) => {
          if (reason instanceof Error && reason.message === "explanation_unavailable") {
            setLegacyRun(true);
            return;
          }
          setError(reason instanceof Error ? reason.message : "radar.error");
        });
    },
    [profileId],
  );

  const loadMatches = useCallback(
    (run: string | null) => {
      radarApi
        .matches(profileId, run, PAGE_SIZE, null)
        .then((page) => {
          // Si el run pedido está aún pending/failed y no trae items, fallback al último succeeded para no dejar el mapa vacío
          if (page.run_state !== "succeeded" && page.items.length === 0 && run !== null) {
            radarApi
              .matches(profileId, null, PAGE_SIZE, null)
              .then((fallback) => {
                if (fallback.items.length > 0) {
                  setItems(fallback.items);
                  setNextAfter(fallback.next_after_position);
                  const states: Record<string, FeedbackEventType | null> = {};
                  for (const item of fallback.items) states[item.listing_id] = item.decision_state ?? null;
                  setDecisionStates(states);
                  if (fallback.run_state === "succeeded") loadExplanations(fallback.run_id);
                  fallback.items.forEach((item) => {
                    const key = `${fallback.run_id}:${item.listing_id}`;
                    if (!emittedRef.current.has(key)) {
                      emittedRef.current.add(key);
                      emitImpression(profileId, fallback.run_id, item.listing_id);
                    }
                  });
                } else {
                  setItems(page.items);
                  setNextAfter(page.next_after_position);
                }
                setRunId(page.run_id);
                setRunState(page.run_state);
                setError(null);
              })
              .catch(() => {
                setItems(page.items);
                setRunId(page.run_id);
                setRunState(page.run_state);
                setNextAfter(page.next_after_position);
                setError(null);
              });
            return;
          }
          setItems(page.items);
          setRunId(page.run_id);
          setRunState(page.run_state);
          setNextAfter(page.next_after_position);
          setError(null);
          const states: Record<string, FeedbackEventType | null> = {};
          for (const item of page.items) states[item.listing_id] = item.decision_state ?? null;
          setDecisionStates(states);
          if (page.run_state === "succeeded") loadExplanations(page.run_id);
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
    [profileId, loadExplanations],
  );

  useEffect(() => {
    if (isMock) return;
    loadMatches(runId);
  }, [loadMatches, runId, isMock]);

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

  const generating = runState === "pending" || runState === "running";
  const isMapView = items.length > 0;

  // Ocultar footer global y evitar scroll del body en vista mapa — debe estar antes de cualquier early return (Rules of Hooks)
  useEffect(() => {
    if (!isMapView) return;
    const footer = document.querySelector('footer[data-slot="global-attribution"]') as HTMLElement | null;
    const prevDisplay = footer?.style.display ?? "";
    const prevOverflow = document.body.style.overflow;
    const prevHtmlOverflow = document.documentElement.style.overflow;
    if (footer) footer.style.display = "none";
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    return () => {
      if (footer) footer.style.display = prevDisplay;
      document.body.style.overflow = prevOverflow;
      document.documentElement.style.overflow = prevHtmlOverflow;
    };
  }, [isMapView]);

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
          {humanizeError(error)}{" "}
          <Link href="/radar" className="underline">
            Volver a mis radares
          </Link>
          <span className="ml-2 text-xs text-muted-foreground">({error})</span>
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

  if (isMapView) {
    const headerNode = (
      <div className="flex flex-col">
        <div className="flex items-center gap-3 px-4 py-2">
          <h1 className="truncate text-sm font-semibold tracking-tight">{profile.name}</h1>
          <p className="hidden truncate text-xs text-muted-foreground sm:block">
            {profile.zones.length > 0 ? profile.zones.map(neighborhoodLabel).join(", ") : "Sin zonas"} · hasta ${profile.budget_max.toLocaleString("es-AR")} · {profile.min_rooms || "sin"} amb
            <span className="ml-2 hidden text-muted-foreground/60 sm:inline">· {profile.status === "active" ? "activo" : profile.status === "paused" ? "pausado" : "archivado"}</span>
          </p>
          <span className="ml-auto hidden text-xs text-muted-foreground sm:block">{items.length} oportunidades</span>
        </div>
        {legacyRun && !generating && (
          <div className="border-t border-border/60 bg-card px-4 py-1">
            <p className="text-xs text-muted-foreground">La explicación no está disponible para este run. Se regenerará con razones completas.</p>
          </div>
        )}
        {!isMock && (
          <>
            <ProposalBanner profileId={profileId} onDecision={() => setReloadKey((c) => c + 1)} />
            <UpdateProposalBanner profileId={profileId} onDecision={() => setReloadKey((c) => c + 1)} />
          </>
        )}
        {generating && (
          <div className="border-t border-border/60 bg-amber-50 px-4 py-1.5">
            <p className="flex items-center gap-1.5 text-xs text-amber-800">
              <Spinner className="size-3" /> Actualizando resultados… se muestran los anteriores
            </p>
          </div>
        )}
        {runState === "failed" && !generating && (
          <div className="border-t border-amber-200 bg-amber-50 px-4 py-1.5">
            <p className="text-xs text-amber-800">La última generación falló — mostrando resultados anteriores. Podés reintentar o ajustar el radar.</p>
          </div>
        )}
      </div>
    );
    return (
      <main data-fullscreen="true" className="flex h-[100dvh] w-full max-w-none overflow-hidden bg-background" id="main-content">
        <RadarShell
          header={headerNode}
          radars={allRadars.length ? allRadars : profile ? [profile] : []}
          selectedRadarId={profileId}
          matches={items}
          explanations={explanations}
        />
        {error && (
          <div className="pointer-events-none fixed left-[280px] top-[41px] z-20 max-w-xl px-4 sm:left-[296px]">
            <Alert role="alert" className="pointer-events-auto py-2 shadow-md">
              <span className="text-sm">{humanizeError(error)}</span>{" "}
              <Button className="ml-2 h-7 px-2.5 text-xs bg-muted text-foreground hover:bg-muted/80" onClick={() => setReloadKey((c) => c + 1)}>
                Reintentar
              </Button>
            </Alert>
          </div>
        )}
        {nextAfter !== null && (
          <div className="fixed bottom-3 left-1/2 z-20 -translate-x-1/2 rounded-full border border-border bg-card px-2 py-1 shadow-md">
            <Button className="h-7 bg-muted px-3 text-xs text-foreground hover:bg-muted/80" onClick={() => void loadMore()}>
              Cargar más
            </Button>
          </div>
        )}
      </main>
    );
  }
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-4 sm:px-6" id="main-content">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b border-border/60 pb-3">
        <div className="min-w-0 flex-1">
          <h1 className="break-words text-2xl font-semibold tracking-tight [overflow-wrap:anywhere] sm:text-3xl">{profile.name}</h1>
          <p className="break-words text-sm text-muted-foreground [overflow-wrap:anywhere]">
            {profile.zones.length > 0 ? profile.zones.map(neighborhoodLabel).join(", ") : "Sin zonas"} · hasta ${profile.budget_max.toLocaleString("es-AR")} · {profile.min_rooms || "sin"} amb
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {profile.status === "active" && (
            <Button className="h-7 px-2.5 text-xs bg-muted text-foreground hover:bg-muted/80" onClick={() => void changeStatus("paused")}>
              Pausar
            </Button>
          )}
          {profile.status === "paused" && (
            <Button className="h-7 px-2.5 text-xs bg-muted text-foreground hover:bg-muted/80" onClick={() => void changeStatus("active")}>
              Reanudar
            </Button>
          )}
          {profile.status !== "archived" && (
            <Button className="h-7 px-2.5 text-xs bg-muted text-foreground hover:bg-muted/80" onClick={() => void changeStatus("archived")}>
              Archivar
            </Button>
          )}
          <Link href={`/radar/${profileId}/compare`}>
            <Button className="h-7 px-2.5 text-xs bg-muted text-foreground hover:bg-muted/80">Comparar</Button>
          </Link>
          <Link href={`/radar/${profileId}/shortlist`}>
            <Button className="h-7 px-2.5 text-xs bg-muted text-foreground hover:bg-muted/80">Guardados</Button>
          </Link>
          <Link href={`/radar/${profileId}/dismissed`}>
            <Button className="h-7 px-2.5 text-xs bg-muted text-foreground hover:bg-muted/80">Descartados</Button>
          </Link>
        </div>
      </div>

      {error && (
        <Alert role="alert" className="py-2">
          <span className="text-sm">{humanizeError(error)}</span>{" "}
          <Button
            className="ml-2 h-7 px-2.5 text-xs bg-muted text-foreground hover:bg-muted/80"
            onClick={() => setReloadKey((current) => current + 1)}
          >
            Reintentar
          </Button>
        </Alert>
      )}

      {generating && (
        <div className="mb-3 flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <Spinner /> Generando resultados…
        </div>
      )}

      {legacyRun && !generating && (
        <Alert role="status" className="py-2 text-sm">
          La explicación no está disponible para este run. Se regenerará con razones completas.
        </Alert>
      )}

      {!isMock && <ProposalBanner profileId={profileId} onDecision={() => setReloadKey((current) => current + 1)} />}
      {!isMock && <UpdateProposalBanner profileId={profileId} onDecision={() => setReloadKey((current) => current + 1)} />}

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

      {runState !== "succeeded" && (
        <section className="mt-6" aria-label="Chat con Umbral">
          <ChatPanel
            profileId={profileId}
            onDecisionApplied={() => setReloadKey((current) => current + 1)}
          />
        </section>
      )}
    </main>
  );
}
