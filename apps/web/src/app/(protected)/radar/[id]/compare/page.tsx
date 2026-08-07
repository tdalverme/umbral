"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { radarApi, type Comparison, type MatchItem, type SearchProfile } from "@/lib/radar/client";
import { emitComparisonViewed } from "@/lib/radar/events";

const PAGE_SIZE = 100;

export default function ComparePage(): React.ReactElement {
  const params = useParams<{ id: string }>();
  const profileId = params.id;

  const [profile, setProfile] = useState<SearchProfile | null>(null);
  const [matches, setMatches] = useState<MatchItem[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    radarApi
      .getProfile(profileId)
      .then((value) => {
        setProfile(value);
        return radarApi.matches(profileId, value.latest_run?.run_id ?? null, PAGE_SIZE, null);
      })
      .then((page) => {
        setMatches(page.items);
        return radarApi.getShortlist(profileId);
      })
      .then((shortlist) => {
        setSelected(shortlist.listing_ids);
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "radar.error");
      });
  }, [profileId]);

  const toggle = useCallback(
    (listingId: string) => {
      setSelected((current) =>
        current.includes(listingId)
          ? current.filter((item) => item !== listingId)
          : [...current, listingId],
      );
    },
    [],
  );

  async function saveAndCompare(): Promise<void> {
    setError(null);
    try {
      await radarApi.setShortlist(profileId, selected);
      if (selected.length < 2) {
        setError("comparison.limit_min");
        return;
      }
      const result = await radarApi.comparison(profileId, selected);
      setComparison(result);
      const run = profile?.latest_run?.run_id ?? "";
      if (run) emitComparisonViewed(profileId, run, selected.length, result.score_version);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "radar.error");
    }
  }

  const loading = profile === null;

  if (loading) {
    return (
      <main className="mx-auto w-full max-w-6xl px-6 py-16" id="main-content">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Spinner /> Cargando comparador…
        </div>
      </main>
    );
  }

  const byId = new Map(matches.map((item) => [item.listing_id, item]));
  const selectedItems = selected
    .map((listingId) => byId.get(listingId))
    .filter((item): item is MatchItem => item !== undefined);

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-16" id="main-content">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-4xl font-semibold tracking-tight">Comparar</h1>
          <p className="text-muted-foreground">
            {profile.name} · seleccioná entre {Math.min(matches.length, 6)} propiedades del radar
          </p>
        </div>
        <div className="flex gap-2">
          <Link href={`/radar/${profileId}`}>
            <Button className="bg-muted text-foreground hover:bg-muted/80">Volver al radar</Button>
          </Link>
          <Button onClick={() => void saveAndCompare()}>Comparar selección</Button>
        </div>
      </div>

      {error && (
        <Alert role="alert">
          Ocurrió un error ({error}). Seleccioná entre 2 y 6 propiedades del mismo radar.
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {matches.map((item) => {
          const active = selected.includes(item.listing_id);
          return (
            <Card key={item.listing_id} className={active ? "border-ring" : ""}>
              <CardHeader>
                <CardTitle className="text-lg">
                  {item.neighborhood ?? "Barrio no declarado"} · $
                  {Number(item.total_cost ?? 0).toLocaleString("es-AR")}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p className="text-muted-foreground">
                  {item.surface_m2 !== null ? `${item.surface_m2} m²` : "sin superficie"} ·{" "}
                  {item.rooms !== null ? `${item.rooms} ambientes` : "sin ambientes"}
                </p>
                <Button
                  className="min-h-8 w-full bg-muted px-3 text-xs text-foreground hover:bg-muted/80"
                  aria-pressed={active}
                  onClick={() => toggle(item.listing_id)}
                >
                  {active ? "Quitar de la selección" : "Agregar a la selección"}
                </Button>
                <Link href={`/listings/${item.listing_id}?profile=${profileId}`} className="block text-xs underline">
                  Ver detalle
                </Link>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {comparison && (
        <section className="mt-10" aria-label="matriz de comparación">
          <h2 className="mb-4 text-2xl font-semibold">Matriz de comparación</h2>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr>
                  <th scope="col" className="border-b p-2 text-left font-medium">
                    Dimensión
                  </th>
                  {comparison.listings.map((listing) => (
                    <th key={listing.listing_id} scope="col" className="border-b p-2 text-left font-medium">
                      {byId.get(listing.listing_id)?.neighborhood ?? "Propiedad"}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {comparison.dimensions.map((dimension) => (
                  <tr key={dimension.key}>
                    <th scope="row" className="border-b p-2 text-left text-muted-foreground">
                      {dimension.label}
                    </th>
                    {comparison.listings.map((listing) => {
                      const cell = comparison.cells.find(
                        (item) => item.listing_id === listing.listing_id && item.dimension_key === dimension.key,
                      );
                      return (
                        <td key={listing.listing_id} className="border-b p-2">
                          {cell?.missing ? (
                            <span className="text-muted-foreground">sin datos</span>
                          ) : (
                            <span>{String(cell?.value ?? "—")}</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            La comparación muestra datos disponibles y faltantes; no declara un ganador.
          </p>
        </section>
      )}
    </main>
  );
}
