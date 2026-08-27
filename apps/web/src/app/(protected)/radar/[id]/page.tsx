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
          <Link href={`/radar/${profileId}/compare`}>
            <Button className="min-h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80">Comparar</Button>
          </Link>
          <Link href={`/radar/${profileId}/shortlist`}>
            <Button className="min-h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80">Guardados</Button>
          </Link>
          <Link href={`/radar/${profileId}/dismissed`}>
            <Button className="min-h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80">Descartados</Button>
          </Link>
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

      {legacyRun && !generating && (
        <Alert role="status">
          La explicación no está disponible para este run. Los resultados se generarán con razones completas en el próximo
          run.
        </Alert>
      )}

      <ProposalBanner profileId={profileId} onDecision={() => setReloadKey((current) => current + 1)} />
      <UpdateProposalBanner profileId={profileId} onDecision={() => setReloadKey((current) => current + 1)} />

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
        <RadarShell radars={profile ? [profile] : []} selectedRadarId={profileId} matches={items.slice(0, 8)} />
      )}

      {runState === "succeeded" && items.length > 0 && nextAfter !== null && (
        <div className="mt-6 flex justify-center">
          <Button className="bg-muted text-foreground hover:bg-muted/80" onClick={() => void loadMore()}>
            Cargar más
          </Button>
        </div>
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
