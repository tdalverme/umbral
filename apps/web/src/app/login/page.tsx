"use client";

import { FormEvent, useEffect, useState } from "react";
import type { ReactElement } from "react";

const previewDevEnabledStatic = process.env.NEXT_PUBLIC_PREVIEW_DEV_LOGIN_ENABLED === "1";

export default function LoginPage(): ReactElement {
  const [email, setEmail] = useState("");
  const [devEmail, setDevEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [devError, setDevError] = useState<string | null>(null);
  const [devLoading, setDevLoading] = useState(false);
  const [devEnabled, setDevEnabled] = useState(previewDevEnabledStatic);
  useEffect(() => {
    if (!previewDevEnabledStatic && typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (params.get("dev") === "1" || params.get("preview") === "1") setDevEnabled(true);
    }
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await fetch("/api/auth/magic-link-requests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) });
    setSent(true);
  }
  async function submitDev(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setDevError(null);
    setDevLoading(true);
    const res = await fetch("/api/auth/dev-login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: devEmail }) });
    setDevLoading(false);
    if (res.ok) {
      window.location.href = "/";
      return;
    }
    const text = await res.text();
    setDevError(text || `Error ${res.status}`);
  }
  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-6 p-6">
      <h1 className="text-3xl font-semibold">Entrar a Umbral</h1>
      {sent ? (
        <p>Si la dirección está habilitada, recibirás un enlace para continuar.</p>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
          <button type="submit">Enviar enlace</button>
        </form>
      )}
      {devEnabled ? (
        <section className="mt-8 rounded border border-dashed p-4">
          <h2 className="text-sm font-semibold">Acceso rápido (solo preview)</h2>
          <p className="mb-3 text-xs text-muted-foreground">Crea sesión sin magic link. Requiere PREVIEW_DEV_LOGIN_TOKEN en el servidor.</p>
          <form onSubmit={submitDev} className="flex flex-col gap-2">
            <label htmlFor="devEmail" className="text-sm">Email dev</label>
            <input id="devEmail" type="email" required value={devEmail} onChange={(event) => setDevEmail(event.target.value)} placeholder="test@preview.local" />
            <button type="submit" disabled={devLoading} className="rounded bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50">
              {devLoading ? "Entrando…" : "Entrar sin link"}
            </button>
            {devError ? <p className="text-xs text-red-600">{devError}</p> : null}
          </form>
        </section>
      ) : null}
    </main>
  );
}
