"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { radarApi } from "@/lib/radar/client";
import { CABA_NEIGHBORHOODS, neighborhoodLabel } from "@/lib/radar/neighborhoods";

interface Draft {
  name: string;
  zones: string[];
  budgetMax: string;
  budgetMin: string;
  minRooms: string;
  surfaceMin: string;
  surfaceMax: string;
}

const EMPTY_DRAFT: Draft = { name: "", zones: [], budgetMax: "", budgetMin: "", minRooms: "0", surfaceMin: "", surfaceMax: "" };

export default function NewRadarPage(): React.ReactElement {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function update(patch: Partial<Draft>): void {
    setDraft((current) => ({ ...current, ...patch }));
  }

  function toggleZone(zone: string): void {
    setDraft((current) => ({
      ...current,
      zones: current.zones.includes(zone)
        ? current.zones.filter((item) => item !== zone)
        : [...current.zones, zone],
    }));
  }

  async function submit(): Promise<void> {
    setSubmitting(true);
    setError(null);
    try {
      const profile = await radarApi.createProfile({
        name: draft.name,
        zones: draft.zones,
        budget_max: Number(draft.budgetMax),
        budget_min: draft.budgetMin ? Number(draft.budgetMin) : null,
        min_rooms: Number(draft.minRooms || 0),
        surface_min: draft.surfaceMin ? Number(draft.surfaceMin) : null,
        surface_max: draft.surfaceMax ? Number(draft.surfaceMax) : null,
        unknown_strategy: null,
      });
      router.push(`/radar/${profile.search_profile_id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "radar.error");
      setSubmitting(false);
    }
  }

  const budgetValid = Number(draft.budgetMax) > 0;
  const zonesValid = draft.zones.length > 0;
  const nameValid = draft.name.trim().length > 0;

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-3xl flex-col justify-center px-6 py-16" id="main-content">
      <Card>
        <CardHeader>
          <CardTitle className="text-4xl font-semibold tracking-tight">Creá tu radar</CardTitle>
          <CardDescription>
            Paso {step} de 3 — definí cómo querés vivir para que empecemos a buscar por vos.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {step === 1 && (
            <div className="space-y-4">
              <Field>
                <FieldLabel htmlFor="radar-name">Nombre del radar</FieldLabel>
                <Input
                  id="radar-name"
                  value={draft.name}
                  maxLength={80}
                  onChange={(event) => update({ name: event.target.value })}
                  aria-invalid={!nameValid}
                />
              </Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field>
                  <FieldLabel htmlFor="budget-max">Presupuesto máximo por mes (ARS)</FieldLabel>
                  <Input
                    id="budget-max"
                    type="number"
                    min={1}
                    value={draft.budgetMax}
                    onChange={(event) => update({ budgetMax: event.target.value })}
                    aria-invalid={!budgetValid}
                  />
                  {!budgetValid && <FieldError id="budget-max-error">Ingresá un presupuesto mayor a cero.</FieldError>}
                </Field>
                <Field>
                  <FieldLabel htmlFor="budget-min">Presupuesto mínimo (opcional)</FieldLabel>
                  <Input
                    id="budget-min"
                    type="number"
                    min={0}
                    value={draft.budgetMin}
                    onChange={(event) => update({ budgetMin: event.target.value })}
                  />
                </Field>
              </div>
              <div className="flex justify-end">
                <Button disabled={!budgetValid || !nameValid} onClick={() => setStep(2)}>
                  Siguiente
                </Button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <fieldset>
                <legend className="mb-2 text-sm font-medium">¿En qué barrios querés vivir?</legend>
                <div className="grid gap-2 sm:grid-cols-2">
                  {CABA_NEIGHBORHOODS.map((neighborhood) => {
                    const selected = draft.zones.includes(neighborhood.value);
                    return (
                      <label key={neighborhood.value} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => toggleZone(neighborhood.value)}
                          className="size-4"
                        />
                        {neighborhood.label}
                      </label>
                    );
                  })}
                </div>
                {!zonesValid && <FieldError id="zones-error">Elegí al menos un barrio.</FieldError>}
              </fieldset>
              <div className="flex justify-between">
                <Button className="bg-muted text-foreground hover:bg-muted/80" onClick={() => setStep(1)}>
                  Volver
                </Button>
                <Button disabled={!zonesValid} onClick={() => setStep(3)}>
                  Siguiente
                </Button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-3">
                <Field>
                  <FieldLabel htmlFor="min-rooms">Ambientes mínimos</FieldLabel>
                  <Input
                    id="min-rooms"
                    type="number"
                    min={0}
                    max={200}
                    value={draft.minRooms}
                    onChange={(event) => update({ minRooms: event.target.value })}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="surface-min">Superficie mínima (m², opcional)</FieldLabel>
                  <Input
                    id="surface-min"
                    type="number"
                    min={0}
                    value={draft.surfaceMin}
                    onChange={(event) => update({ surfaceMin: event.target.value })}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="surface-max">Superficie máxima (m², opcional)</FieldLabel>
                  <Input
                    id="surface-max"
                    type="number"
                    min={0}
                    value={draft.surfaceMax}
                    onChange={(event) => update({ surfaceMax: event.target.value })}
                  />
                </Field>
              </div>
              <Card className="bg-muted/40">
                <CardHeader>
                  <CardTitle className="text-lg">Resumen</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-sm">
                  <p>
                    <strong>Nombre:</strong> {draft.name}
                  </p>
                  <p>
                    <strong>Barrios:</strong> {draft.zones.map(neighborhoodLabel).join(", ")}
                  </p>
                  <p>
                    <strong>Presupuesto:</strong> $
                    {Number(draft.budgetMax).toLocaleString("es-AR")}
                    {draft.budgetMin ? ` (mínimo $${Number(draft.budgetMin).toLocaleString("es-AR")})` : ""}
                  </p>
                  <p>
                    <strong>Ambientes:</strong> {draft.minRooms || "sin mínimo"}
                  </p>
                  <p>
                    <strong>Superficie:</strong>{" "}
                    {draft.surfaceMin || draft.surfaceMax
                      ? `${draft.surfaceMin || "—"} a ${draft.surfaceMax || "—"} m²`
                      : "sin límite"}
                  </p>
                </CardContent>
              </Card>
              {error && <Alert role="alert">No se pudo crear el radar ({error}). Revisá los datos e intentá de nuevo.</Alert>}
              <div className="flex justify-between">
                <Button className="bg-muted text-foreground hover:bg-muted/80" onClick={() => setStep(2)} disabled={submitting}>
                  Volver
                </Button>
                <Button onClick={() => void submit()} disabled={submitting}>
                  {submitting ? "Creando…" : "Confirmar y crear radar"}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
