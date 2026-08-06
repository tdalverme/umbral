"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { radarApi, type ProfileStatus, type SearchProfile } from "@/lib/radar/client";
import { neighborhoodLabel } from "@/lib/radar/neighborhoods";

const TABS: Array<{ value: ProfileStatus | "all"; label: string }> = [
  { value: "all", label: "Todas" },
  { value: "active", label: "Activas" },
  { value: "paused", label: "Pausadas" },
  { value: "archived", label: "Archivadas" },
];

export default function RadarPage(): React.ReactElement {
  const [tab, setTab] = useState<ProfileStatus | "all">("all");
  const [reloadKey, setReloadKey] = useState(0);
  const [profiles, setProfiles] = useState<SearchProfile[] | null>(null);
  const [loadedForTab, setLoadedForTab] = useState<ProfileStatus | "all" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    radarApi
      .listProfiles(tab === "all" ? undefined : tab)
      .then((items) => {
        setProfiles(items);
        setLoadedForTab(tab);
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "radar.error");
      });
  }, [tab, reloadKey]);

  const loading = profiles === null || loadedForTab !== tab;

  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-16" id="main-content">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-semibold tracking-tight">Mis radares</h1>
          <p className="text-muted-foreground">Búsquedas activas, pausadas y archivadas.</p>
        </div>
        <Link href="/radar/new">
          <Button>Crear radar</Button>
        </Link>
      </div>

      <div role="tablist" aria-label="Estado del radar" className="mb-4 flex gap-2">
        {TABS.map((item) => (
          <Button
            key={item.value}
            className={`min-h-8 px-3 text-xs${tab === item.value ? "" : " bg-muted text-foreground hover:bg-muted/80"}`}
            onClick={() => setTab(item.value)}
            role="tab"
            aria-selected={tab === item.value}
          >
            {item.label}
          </Button>
        ))}
      </div>

      {error && (
        <Card role="alert">
          <CardContent className="py-4">
            No se pudieron cargar los radares ({error}).{" "}
            <Button className="min-h-8 bg-muted px-3 text-xs text-foreground hover:bg-muted/80" onClick={() => setReloadKey((current) => current + 1)}>
              Reintentar
            </Button>
          </CardContent>
        </Card>
      )}

      {!error && loading && (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Spinner /> Cargando radares…
        </div>
      )}

      {!error && !loading && profiles !== null && profiles.length === 0 && (
        <Card>
          <CardHeader>
            <CardTitle>No hay radares {tab !== "all" ? `${tab}s` : ""} todavía</CardTitle>
            <CardDescription>Creá tu primer radar para empezar a recibir oportunidades.</CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/radar/new">
              <Button>Crear radar</Button>
            </Link>
          </CardContent>
        </Card>
      )}

      {!error && !loading && profiles !== null && profiles.length > 0 && (
        <ul className="space-y-3">
          {profiles.map((profile) => (
            <li key={profile.search_profile_id}>
              <Link href={`/radar/${profile.search_profile_id}`} className="block">
                <Card className="transition-colors hover:border-ring">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-xl">{profile.name}</CardTitle>
                      <span className="text-xs uppercase text-muted-foreground">{profile.status}</span>
                    </div>
                    <CardDescription>
                      {profile.zones.map(neighborhoodLabel).join(", ")} · hasta $
                      {profile.budget_max.toLocaleString("es-AR")} · {profile.min_rooms || "sin"} ambientes
                    </CardDescription>
                  </CardHeader>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
