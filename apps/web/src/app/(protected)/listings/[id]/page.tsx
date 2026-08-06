"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { radarApi, type ListingDetail } from "@/lib/radar/client";
import { emitDetailViewed, emitSourceOpened } from "@/lib/radar/events";
import { neighborhoodLabel } from "@/lib/radar/neighborhoods";

export default function ListingDetailPage(): React.ReactElement {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const listingId = params.id;
  const profileId = searchParams.get("profile") ?? "";
  const runId = searchParams.get("run") ?? "";

  const [detail, setDetail] = useState<ListingDetail | null>(null);
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
          <CardContent className="space-y-2 text-sm">
            <p className="text-muted-foreground">
              Aproximación de ajuste a tu radar, sin evidencia: el desglose completo llega más adelante.
            </p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Presupuesto: encaja dentro del máximo declarado</li>
              <li>Ambientes: compatible con el mínimo pedido</li>
              <li>Superficie: dentro de los rangos declarados</li>
              <li>Ubicación: dentro de los barrios elegidos</li>
            </ul>
          </CardContent>
        </Card>
      </div>

      {detail.normalization_errors.length > 0 && (
        <Alert role="alert" className="mt-4">
          Este listado tiene datos faltantes o con errores de origen: {detail.normalization_errors.join(", ")}.
        </Alert>
      )}

      {detail.known_changes.length > 0 && (
        <Card className="mt-4">
          <CardHeader>
            <CardTitle className="text-lg">Cambios conocidos</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {detail.known_changes.map((change, index) => (
              <p key={`${change.field}-${index}`}>
                <strong>{change.field}:</strong> {String(change.before)} → {String(change.after)}
              </p>
            ))}
          </CardContent>
        </Card>
      )}

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
