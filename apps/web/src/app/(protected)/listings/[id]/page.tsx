"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { FeedbackActions } from "@/components/radar/feedback-actions";
import { radarApi, type Explanation, type ListingDetail } from "@/lib/radar/client";
import { emitDetailViewed, emitExplanationViewed, emitSourceOpened } from "@/lib/radar/events";
import { neighborhoodLabel } from "@/lib/radar/neighborhoods";

const EVIDENCE_LABEL: Record<string, string> = { strong: "fuerte", medium: "media", low: "baja" };

function Breakdown({ explanation }: { explanation: Explanation }): React.ReactElement {
  return (
    <CardContent className="space-y-3 text-sm">
      <p>
        <strong>Confianza del match:</strong> {explanation.confidence.toFixed(2)} ·{" "}
        <strong>Score:</strong> {explanation.score.toFixed(2)} (indicador con confianza, no certeza)
      </p>
      {explanation.satisfied_filters.length > 0 && (
        <p>
          <strong>Filtros cumplidos:</strong> {explanation.satisfied_filters.join(", ")}
        </p>
      )}
      {explanation.reasons.length > 0 && (
        <ul className="space-y-1">
          {explanation.reasons.map((reason) => (
            <li key={reason.criterion_key} className="flex items-start gap-2">
              <span>{reason.text}</span>
              <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                evidencia {EVIDENCE_LABEL[reason.evidence_level]}
              </span>
            </li>
          ))}
        </ul>
      )}
      {explanation.risks.length > 0 && (
        <div>
          <p className="font-medium">Riesgos e incertidumbre</p>
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            {explanation.risks.map((risk) => (
              <li key={`${risk.criterion_key}-${risk.state}`}>{risk.text}</li>
            ))}
          </ul>
        </div>
      )}
      {explanation.missing_data.length > 0 && (
        <p className="text-muted-foreground">
          <strong>Sin datos para evaluar:</strong> {explanation.missing_data.join(", ")}
        </p>
      )}
    </CardContent>
  );
}

export default function ListingDetailPage(): React.ReactElement {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const listingId = params.id;
  const profileId = searchParams.get("profile") ?? "";
  const runId = searchParams.get("run") ?? "";

  const [detail, setDetail] = useState<ListingDetail | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [explanationError, setExplanationError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    radarApi
      .listing(listingId)
      .then((value) => {
        setDetail(value);
        setError(null);
        if (profileId && runId) emitDetailViewed(profileId, runId, listingId);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "radar.error");
      });
  }, [listingId, profileId, runId]);

  useEffect(() => {
    if (!profileId || !runId) return;
    radarApi
      .explanation(profileId, listingId, runId)
      .then((value) => {
        setExplanation(value);
        setExplanationError(null);
        emitExplanationViewed(profileId, value.run_id, listingId, value.score_version);
      })
      .catch((reason: unknown) => {
        setExplanationError(reason instanceof Error ? reason.message : "radar.error");
      });
  }, [profileId, listingId, runId]);

  const loading = detail === null && error === null;

  if (loading) {
    return (
      <main className="mx-auto w-full max-w-3xl px-6 py-16" id="main-content">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Spinner /> Cargando detalle…
        </div>
      </main>
    );
  }

  if (error || !detail) {
    return (
      <main className="mx-auto w-full max-w-3xl px-6 py-16" id="main-content">
        <Alert role="alert">
          No se pudo cargar el detalle ({error ?? "radar.listing_not_accessible"}).{" "}
          {profileId ? (
            <Link href={`/radar/${profileId}`} className="underline">
              Volver al radar
            </Link>
          ) : (
            <Link href="/radar" className="underline">
              Volver a mis radares
            </Link>
          )}
        </Alert>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-16" id="main-content">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-semibold tracking-tight">
            {detail.neighborhood ? neighborhoodLabel(detail.neighborhood) : "Propiedad"}
          </h1>
          <p className="text-muted-foreground">
            ${detail.total_cost.toLocaleString("es-AR")} por mes · {detail.property_type} ·{" "}
            {detail.rooms !== null ? `${detail.rooms} ambientes` : "ambientes no declarados"}
          </p>
        </div>
        {profileId && (
          <Link href={`/radar/${profileId}`}>
            <Button className="bg-muted text-foreground hover:bg-muted/80">Volver al radar</Button>
          </Link>
        )}
      </div>

      {detail.url && (
        <div className="mb-4">
          <Button
            onClick={() => {
              if (profileId && runId) emitSourceOpened(profileId, runId, listingId, detail.source_id);
              window.open(detail.url!, "_blank", "noopener,noreferrer");
            }}
          >
            Ver publicación original
          </Button>
        </div>
      )}

      {profileId && (
        <div className="mb-4">
          <FeedbackActions profileId={profileId} listingId={listingId} runId={runId || null} />
        </div>
      )}

      {profileId && (
        <div className="mb-4">
          <Link
            href={`/radar/${profileId}?chat_context=listing:${listingId}`}
            className="text-sm font-medium underline-offset-4 hover:underline"
          >
            Preguntar sobre este listing en el chat
          </Link>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Datos</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>
              <strong>Precio:</strong> ${detail.price_value.toLocaleString("es-AR")} {detail.price_currency}
            </p>
            <p>
              <strong>Expensas:</strong>{" "}
              {detail.expenses_value !== null
                ? `$${detail.expenses_value.toLocaleString("es-AR")}`
                : "no declaradas"}
            </p>
            <p>
              <strong>Costo total:</strong> ${detail.total_cost.toLocaleString("es-AR")}
            </p>
            <p>
              <strong>Superficie:</strong>{" "}
              {detail.surface_m2 !== null ? `${detail.surface_m2} m²` : "no declarada"}
            </p>
            <p>
              <strong>Ambientes:</strong> {detail.rooms !== null ? detail.rooms : "no declarados"}
            </p>
            <p>
              <strong>Dormitorios:</strong> {detail.bedrooms !== null ? detail.bedrooms : "no declarados"}
            </p>
            <p>
              <strong>Piso:</strong> {detail.floor !== null ? detail.floor : "no declarado"}
            </p>
            <p>
              <strong>Precisión de ubicación:</strong> {detail.geo_precision}
            </p>
            <p>
              <strong>Fuente:</strong> {detail.source_id}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Por qué aparece acá</CardTitle>
          </CardHeader>
          {explanation ? (
            <Breakdown explanation={explanation} />
          ) : explanationError === "explanation_unavailable" ? (
            <CardContent className="space-y-2 text-sm">
              <p className="text-muted-foreground">
                La explicación no está disponible para este run; se generará con razones completas en el próximo run.
              </p>
              <ul className="list-disc space-y-1 pl-5">
                <li>Presupuesto: encaja dentro del máximo declarado</li>
                <li>Ambientes: compatible con el mínimo pedido</li>
                <li>Superficie: dentro de los rangos declarados</li>
                <li>Ubicación: dentro de los barrios elegidos</li>
              </ul>
            </CardContent>
          ) : (
            <CardContent className="space-y-2 text-sm">
              <p className="text-muted-foreground">Cargando razones…</p>
            </CardContent>
          )}
        </Card>
      </div>

      {detail.normalization_errors.length > 0 && (
        <Alert role="alert" className="mt-4">
          Este listado tiene datos faltantes o con errores de origen: {detail.normalization_errors.join(", ")}.
        </Alert>
      )}

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-lg">Historial de precio y cambios</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          {detail.known_changes.length > 0 ? (
            detail.known_changes.map((change, index) => (
              <p key={`${change.field}-${index}`}>
                <strong>{change.field}:</strong> {String(change.before)} → {String(change.after)}
                {change.observed_at ? ` · ${change.observed_at}` : ""}
                {change.source ? ` · fuente ${change.source}` : ""}
              </p>
            ))
          ) : (
            <p className="text-muted-foreground">
              Historial insuficiente: todavía no hay suficientes versiones observadas para mostrar cambios confirmados.
            </p>
          )}
          <p className="pt-1 text-xs text-muted-foreground">
            Se muestran solo cambios confirmados con su fecha y fuente; no se infieren tendencias con muestra
            insuficiente.
          </p>
        </CardContent>
      </Card>

      {detail.description_text && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="text-lg">Descripción</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-line text-sm">{detail.description_text}</p>
          </CardContent>
        </Card>
      )}
    </main>
  );
}
