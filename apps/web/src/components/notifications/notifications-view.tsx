"use client";

import { useEffect, useState, type ReactNode } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import {
  notificationsApi,
  type InboxItem,
  type NotificationPreferences,
} from "@/lib/notifications/client";

export function NotificationsView({
  initialPreferences,
}: {
  initialPreferences: NotificationPreferences | null;
}): ReactNode {
  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <header>
        <h1 className="text-xl font-semibold">Notificaciones</h1>
        <p className="text-sm text-muted-foreground">
          Oportunidades de tu radar y preferencias de alerta.
        </p>
      </header>
      <AlertPreferencesForm initial={initialPreferences} />
      <InboxList />
    </main>
  );
}

function AlertPreferencesForm({
  initial,
}: {
  initial: NotificationPreferences | null;
}): ReactNode {
  const [prefs, setPrefs] = useState<NotificationPreferences | null>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = async (field: "email_enabled" | "inbox_enabled" | "digest_enabled") => {
    if (!prefs) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await notificationsApi.updatePreferences({
        email_enabled: prefs.email_enabled,
        inbox_enabled: prefs.inbox_enabled,
        timezone: prefs.timezone,
        quiet_hours_start: prefs.quiet_hours_start,
        quiet_hours_end: prefs.quiet_hours_end,
        digest_enabled: prefs.digest_enabled,
        digest_local_hour: prefs.digest_local_hour,
        score_threshold: prefs.score_threshold,
        state: prefs.state,
        ...{ [field]: !prefs[field] },
      });
      setPrefs(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "error");
    } finally {
      setSaving(false);
    }
  };

  const disableAll = async () => {
    if (!prefs) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await notificationsApi.updatePreferences({
        email_enabled: false,
        inbox_enabled: false,
        timezone: prefs.timezone,
        quiet_hours_start: prefs.quiet_hours_start,
        quiet_hours_end: prefs.quiet_hours_end,
        digest_enabled: prefs.digest_enabled,
        digest_local_hour: prefs.digest_local_hour,
        score_threshold: prefs.score_threshold,
        state: "disabled",
      });
      setPrefs(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "error");
    } finally {
      setSaving(false);
    }
  };

  if (!prefs) {
    return (
      <Card>
        <CardContent className="py-4">
          <p className="text-sm text-muted-foreground">Sin preferencias configuradas.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Preferencias de alerta</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {error && <Alert className="border-destructive">{error}</Alert>}
        <label className="flex items-center justify-between gap-3">
          <span>Email</span>
          <input
            type="checkbox"
            checked={prefs.email_enabled}
            disabled={saving}
            onChange={() => toggle("email_enabled")}
            aria-label="Activar alertas por email"
          />
        </label>
        <label className="flex items-center justify-between gap-3">
          <span>Inbox web</span>
          <input
            type="checkbox"
            checked={prefs.inbox_enabled}
            disabled={saving}
            onChange={() => toggle("inbox_enabled")}
            aria-label="Activar alertas en el inbox"
          />
        </label>
        <label className="flex items-center justify-between gap-3">
          <span>Digest diario</span>
          <input
            type="checkbox"
            checked={prefs.digest_enabled}
            disabled={saving}
            onChange={() => toggle("digest_enabled")}
            aria-label="Activar digest diario"
          />
        </label>
        <p className="text-xs text-muted-foreground">
          Estado: {prefs.state} · Zona horaria {prefs.timezone} · Quiet hours{" "}
          {prefs.quiet_hours_start} a {prefs.quiet_hours_end} · Umbral de score{" "}
          {prefs.score_threshold.toFixed(2)} · Versión {prefs.version}
        </p>
        <Button className="bg-destructive" onClick={disableAll} disabled={saving || prefs.state === "disabled"}>
          Desactivar alertas
        </Button>
      </CardContent>
    </Card>
  );
}

function InboxList(): ReactNode {
  const [items, setItems] = useState<InboxItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    notificationsApi
      .listInbox(50)
      .then((page) => setItems(page.items))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "error"));
  }, []);

  const markRead = async (id: string) => {
    try {
      await notificationsApi.markRead(id, true);
      setItems((current) =>
        (current ?? []).map((item) => (item.decision_id === id ? { ...item, read: true } : item)),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "error");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Centro de notificaciones</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {error && <Alert className="border-destructive">{error}</Alert>}
        {items === null && <Spinner />}
        {items !== null && items.length === 0 && (
          <p className="text-muted-foreground">Sin notificaciones por ahora.</p>
        )}
        {items?.map((item) => (
          <div
            key={item.decision_id}
            className="flex items-center justify-between gap-3 rounded border p-3"
          >
            <div>
              <p className="font-medium">{item.trigger === "new_match" ? "Nuevo match" : "Baja de precio"}</p>
              <p className="text-xs text-muted-foreground">
                {item.reason_code} · {new Date(item.created_at).toLocaleString()}
              </p>
            </div>
            {!item.read && (
              <Button className="bg-secondary" onClick={() => markRead(item.decision_id)}>
                Marcar como leída
              </Button>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
