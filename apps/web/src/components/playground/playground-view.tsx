"use client";

import { useEffect, useState, useTransition } from "react";

import { GeoMap } from "@/components/playground/geo-map";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { displayValue, humanizeKey, profileDiff } from "@/lib/playground/helpers";
import type {
  ConversationTrace,
  GeoInspection,
  JsonRecord,
  PlaygroundFixture,
} from "@/lib/playground/types";

type Lab = "conversation" | "geo";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`No se pudo cargar ${path}`);
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, payload: JsonRecord): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `No se pudo ejecutar ${path}`);
  }
  return response.json() as Promise<T>;
}

export function PlaygroundView(): React.ReactElement {
  const [lab, setLab] = useState<Lab>("conversation");
  const [fixtures, setFixtures] = useState<PlaygroundFixture[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    void getJson<{ fixtures: PlaygroundFixture[] }>("/api/playground/fixtures")
      .then((payload) => setFixtures(payload.fixtures))
      .catch((error: unknown) => setLoadError(error instanceof Error ? error.message : "Error desconocido"));
  }, []);

  const fixture = fixtures[0];

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[1500px] flex-col gap-6 px-4 py-6 outline-none sm:px-8" id="main-content" tabIndex={-1}>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">Umbral / local</p>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">Playground</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">
            Iterá el comportamiento del producto con fixtures aislados: conversación, tools y contexto urbano.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="size-2 rounded-full bg-primary" aria-hidden="true" />
          Sin persistencia · sin release · fixture: {fixture?.id ?? "cargando"}
        </div>
      </header>

      <nav aria-label="Labs del playground" className="flex flex-wrap gap-2 border-b border-border pb-3">
        <Button
          aria-pressed={lab === "conversation"}
          className={lab === "conversation" ? "bg-primary" : "bg-secondary text-secondary-foreground hover:bg-secondary/80"}
          onClick={() => setLab("conversation")}
        >
          Conversation Lab
        </Button>
        <Button
          aria-pressed={lab === "geo"}
          className={lab === "geo" ? "bg-primary" : "bg-secondary text-secondary-foreground hover:bg-secondary/80"}
          onClick={() => setLab("geo")}
        >
          Geo Lab
        </Button>
      </nav>

      {loadError ? (
        <Alert role="alert">
          <AlertTitle>No se pudo cargar el playground</AlertTitle>
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      ) : fixture === undefined ? (
        <p className="text-sm text-muted-foreground" role="status">Cargando fixtures…</p>
      ) : lab === "conversation" ? (
        <ConversationLab fixture={fixture} />
      ) : (
        <GeoLab fixture={fixture} />
      )}
    </main>
  );
}

function ConversationLab({ fixture }: Readonly<{ fixture: PlaygroundFixture }>): React.ReactElement {
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<string[]>([]);
  const [mode, setMode] = useState<"fake" | "real">("fake");
  const [trace, setTrace] = useState<ConversationTrace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const run = (nextTurns: string[]) => {
    setError(null);
    startTransition(() => {
      void postJson<ConversationTrace>("/api/playground/conversations", {
        fixture_id: fixture.id,
        turns: nextTurns,
        model_mode: mode,
      })
        .then(setTrace)
        .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "No se pudo ejecutar el turno"));
    });
  };

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    const nextTurns = [...turns, text];
    setTurns(nextTurns);
    setDraft("");
    run(nextTurns);
  };

  const quickDecision = (text: string) => {
    const nextTurns = [...turns, text];
    setTurns(nextTurns);
    run(nextTurns);
  };

  const profileChanges = trace ? profileDiff(trace.state_before, trace.state_after) : [];
  const hasPendingDecision = trace?.turns.some((turn) => turn.status === "interrupted" && turn.interrupt !== null) ?? false;

  return (
    <section className="grid gap-6 xl:grid-cols-[minmax(22rem,0.85fr)_minmax(34rem,1.5fr)]" aria-labelledby="conversation-lab-title">
      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader>
            <CardTitle id="conversation-lab-title">Probá el flow conversacional</CardTitle>
            <CardDescription>
              Revisá intención, tool calls, pausas de confirmación, estado del perfil y resultado final.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <Field>
              <FieldLabel htmlFor="conversation-mode">Modelo</FieldLabel>
              <select
                className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
                id="conversation-mode"
                value={mode}
                onChange={(event) => setMode(event.target.value as "fake" | "real")}
              >
                <option value="fake">Fake determinístico</option>
                <option value="real">Real / managed gateway</option>
              </select>
            </Field>
            <form className="flex flex-col gap-3" onSubmit={submit}>
              <Field>
                <FieldLabel htmlFor="conversation-input">Mensaje</FieldLabel>
                <textarea
                  className="min-h-28 w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
                  id="conversation-input"
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="Ej.: bajá el presupuesto a 1000"
                  value={draft}
                />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button disabled={isPending || draft.trim().length === 0} type="submit">
                  {isPending ? "Ejecutando…" : "Ejecutar turno"}
                </Button>
                <Button
                  className="bg-secondary text-secondary-foreground hover:bg-secondary/80"
                  disabled={isPending || turns.length === 0}
                  onClick={() => run(turns)}
                >
                  Replay
                </Button>
                <Button
                  className="bg-transparent text-muted-foreground shadow-none hover:bg-muted"
                  disabled={isPending && turns.length === 0}
                  onClick={() => {
                    setTurns([]);
                    setTrace(null);
                    setDraft("");
                    setError(null);
                  }}
                >
                  Limpiar
                </Button>
              </div>
            </form>
            {hasPendingDecision ? (
              <div className="flex flex-col gap-2 rounded-md border border-border bg-muted/40 p-3" aria-live="polite">
                <p className="text-sm font-medium text-foreground">Hay una propuesta esperando decisión.</p>
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => quickDecision("confirmo")}>Confirmar cambio</Button>
                  <Button className="bg-secondary text-secondary-foreground hover:bg-secondary/80" onClick={() => quickDecision("rechazo")}>Rechazar</Button>
                </div>
              </div>
            ) : null}
            {error ? <p className="text-sm text-destructive" role="alert">{error}</p> : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Perfil fixture</CardTitle>
            <CardDescription>Estado que el runner mantiene en memoria para esta ejecución.</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            {Object.entries(trace?.state_after ?? fixture.profile).map(([key, value]) => (
              <div className="flex flex-col gap-1" key={key}>
                <span className="text-xs text-muted-foreground">{humanizeKey(key)}</span>
                <span className="font-medium text-foreground">{displayValue(value)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Trace</CardTitle>
            <CardDescription>{trace ? `run_id ${trace.run_id}` : "Ejecutá un turno para ver evidencia del grafo."}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {trace === null ? (
              <p className="text-sm text-muted-foreground">Sugerencia: probá “bajá el presupuesto a 1000” y luego confirmá.</p>
            ) : (
              <>
                <div className="flex flex-col gap-3" aria-live="polite">
                  {trace.turns.map((turn, index) => (
                    <div className="flex flex-col gap-2 border-b border-border pb-3 last:border-b-0 last:pb-0" key={`${turn.text}-${index}`}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-sm font-medium text-foreground">Turno {index + 1}: {turn.text || "resume"}</span>
                        <code className="text-xs text-muted-foreground">{turn.status}</code>
                      </div>
                      {turn.reply ? <p className="text-sm leading-6 text-foreground">{turn.reply}</p> : null}
                      {turn.tool_calls.length > 0 ? (
                        <div className="flex flex-wrap gap-2 text-xs" aria-label="Tools ejecutadas">
                          {turn.tool_calls.map((call, callIndex) => (
                            <code className="rounded bg-muted px-2 py-1 text-muted-foreground" key={`${call.tool}-${callIndex}`}>
                              {call.tool} · {call.status}
                            </code>
                          ))}
                        </div>
                      ) : null}
                      {turn.interrupt ? (
                        <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs text-muted-foreground">{JSON.stringify(turn.interrupt, null, 2)}</pre>
                      ) : null}
                    </div>
                  ))}
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="flex flex-col gap-2">
                    <h3 className="text-sm font-medium text-foreground">Aserciones rápidas</h3>
                    {trace.assertions.map((assertion) => (
                      <div className="flex items-center justify-between gap-3 text-sm" key={assertion.name}>
                        <span>{humanizeKey(assertion.name)}</span>
                        <code className={assertion.passed ? "text-primary" : "text-destructive"}>{assertion.passed ? "pass" : "fail"}</code>
                      </div>
                    ))}
                  </div>
                  <div className="flex flex-col gap-2">
                    <h3 className="text-sm font-medium text-foreground">Diff de perfil</h3>
                    {profileChanges.length === 0 ? <p className="text-sm text-muted-foreground">Sin cambios.</p> : null}
                    {profileChanges.map((change) => (
                      <div className="grid grid-cols-[1fr_auto_auto] items-center gap-2 text-sm" key={change.key}>
                        <span>{humanizeKey(change.key)}</span>
                        <code className="text-muted-foreground">{displayValue(change.before)}</code>
                        <code className="font-medium text-primary">→ {displayValue(change.after)}</code>
                      </div>
                    ))}
                  </div>
                </div>

                <details>
                  <summary className="cursor-pointer text-sm font-medium text-foreground">Ver eventos y estado bruto</summary>
                  <pre className="mt-3 max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs text-muted-foreground">{JSON.stringify({ events: trace.events, state_after: trace.state_after }, null, 2)}</pre>
                </details>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

function GeoLab({ fixture }: Readonly<{ fixture: PlaygroundFixture }>): React.ReactElement {
  const [listingId, setListingId] = useState(fixture.listings[0]?.id ?? "");
  const [radius, setRadius] = useState("600");
  const [inspection, setInspection] = useState<GeoInspection | null>(null);
  const [selectedSignal, setSelectedSignal] = useState<string | null>(null);
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const listing = fixture.listings.find((item) => item.id === listingId) ?? fixture.listings[0];
  const activeSignal = inspection?.signals.find((signal) => signal.signal === selectedSignal) ?? inspection?.signals[0];
  const selectedFeature = inspection?.features.find((feature) => feature.id === selectedFeatureId);

  const inspect = () => {
    setError(null);
    startTransition(() => {
      void postJson<GeoInspection>("/api/playground/geo", {
        fixture_id: fixture.id,
        listing_id: listingId,
        radius_m: Number(radius),
      })
        .then((result) => {
          setInspection(result);
          setSelectedSignal(result.signals[0]?.signal ?? null);
          setSelectedFeatureId(result.features[0]?.id ?? null);
        })
        .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "No se pudo inspeccionar el listing"));
    });
  };

  return (
    <section className="flex flex-col gap-6" aria-labelledby="geo-lab-title">
      <Card>
        <CardHeader>
          <CardTitle id="geo-lab-title">Inspeccioná el contexto urbano</CardTitle>
          <CardDescription>Seleccioná un listing, ajustá el radio y seguí la línea feature → primitiva → señal.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-4">
          <Field className="min-w-56 flex-1">
            <FieldLabel htmlFor="geo-listing">Listing</FieldLabel>
            <select
              className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
              id="geo-listing"
              value={listingId}
              onChange={(event) => setListingId(event.target.value)}
            >
              {fixture.listings.map((item) => <option key={item.id} value={item.id}>{item.id} · {item.neighborhood ?? "sin barrio"}</option>)}
            </select>
          </Field>
          <Field className="w-36">
            <FieldLabel htmlFor="geo-radius">Radio (m)</FieldLabel>
            <Input id="geo-radius" min={50} max={5000} onChange={(event) => setRadius(event.target.value)} type="number" value={radius} />
          </Field>
          <Button disabled={isPending || listing === undefined} onClick={inspect}>{isPending ? "Calculando…" : "Inspeccionar"}</Button>
          {error ? <p className="w-full text-sm text-destructive" role="alert">{error}</p> : null}
        </CardContent>
      </Card>

      {inspection && listing ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(32rem,1.25fr)_minmax(22rem,0.75fr)]">
          <div className="flex flex-col gap-4">
            <GeoMap
              features={inspection.features}
              listing={inspection.listing}
              onFeatureSelect={setSelectedFeatureId}
              selectedFeatureId={selectedFeatureId}
            />
            <Card>
              <CardHeader>
                <CardTitle>Features alrededor</CardTitle>
                <CardDescription>{inspection.features.length} elementos dentro de {inspection.radius_m} m · snapshot {inspection.snapshot_id}</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-2 sm:grid-cols-2">
                {inspection.features.map((feature) => (
                  <button
                    aria-pressed={feature.id === selectedFeatureId}
                    className="flex flex-col gap-1 rounded-md border border-border bg-background p-3 text-left transition-colors hover:bg-muted aria-pressed:border-primary aria-pressed:bg-muted"
                    key={feature.id}
                    onClick={() => setSelectedFeatureId(feature.id)}
                    type="button"
                  >
                    <span className="text-sm font-medium text-foreground">{feature.name}</span>
                    <span className="text-xs text-muted-foreground">{humanizeKey(feature.category)} · {displayValue(feature.distance_m)} m</span>
                  </button>
                ))}
              </CardContent>
            </Card>
            {selectedFeature ? (
              <Card>
                <CardHeader>
                  <CardTitle>Feature seleccionada</CardTitle>
                  <CardDescription>{selectedFeature.id}</CardDescription>
                </CardHeader>
                <CardContent className="grid grid-cols-2 gap-3 text-sm">
                  <span className="text-muted-foreground">Categoría</span><span>{humanizeKey(selectedFeature.category)}</span>
                  <span className="text-muted-foreground">Distancia</span><span>{displayValue(selectedFeature.distance_m)} m</span>
                  <span className="text-muted-foreground">Tipo</span><span>{selectedFeature.kind}</span>
                </CardContent>
              </Card>
            ) : null}
          </div>

          <div className="flex flex-col gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Señales</CardTitle>
                <CardDescription>Elegí una señal para ver qué términos la componen.</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {inspection.signals.map((signal) => (
                  <button
                    aria-pressed={signal.signal === activeSignal?.signal}
                    className="flex items-center justify-between gap-3 rounded-md border border-border bg-background p-3 text-left hover:bg-muted aria-pressed:border-primary aria-pressed:bg-muted"
                    key={signal.signal}
                    onClick={() => setSelectedSignal(signal.signal)}
                    type="button"
                  >
                    <span className="text-sm font-medium text-foreground">{humanizeKey(signal.signal)}</span>
                    <span className="text-sm tabular-nums text-muted-foreground">{signal.missing ? "sin datos" : `${Math.round(signal.value * 100)}%`}</span>
                  </button>
                ))}
                {activeSignal ? (
                  <div className="mt-2 flex flex-col gap-2 border-t border-border pt-3" aria-live="polite">
                    <div className="flex items-center justify-between gap-3 text-sm"><span>Confianza</span><span>{Math.round(activeSignal.confidence * 100)}%</span></div>
                    <div className="flex flex-col gap-2">
                      {activeSignal.contributors.map((contributor, index) => (
                        <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground" key={`${contributor.term}-${index}`}>
                          <code>{contributor.term}</code><span>{displayValue(contributor.score)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Primitivas</CardTitle>
                <CardDescription>Valores calculados desde los buckets del fixture.</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {inspection.primitives.map((primitive) => (
                  <div className="flex flex-col gap-2 border-b border-border pb-3 last:border-b-0 last:pb-0" key={primitive.category}>
                    <div className="flex items-center justify-between gap-3"><span className="text-sm font-medium">{humanizeKey(primitive.category)}</span><code className="text-xs text-muted-foreground">{primitive.kind}</code></div>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <span className="text-muted-foreground">300m: {displayValue(primitive.count_300m)}</span>
                      <span className="text-muted-foreground">600m: {displayValue(primitive.count_600m)}</span>
                      <span className="text-muted-foreground">nearest: {displayValue(primitive.nearest_m)}</span>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <p className="text-xs text-muted-foreground">{inspection.contract_version} · {inspection.attribution}</p>
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Elegí “Inspeccionar” para abrir el mapa y el lineage urbano.</p>
      )}
    </section>
  );
}
