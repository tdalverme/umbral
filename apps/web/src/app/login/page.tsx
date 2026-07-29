"use client";

import { FormEvent, useState } from "react";
import type { ReactElement } from "react";

export default function LoginPage(): ReactElement {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await fetch("/api/auth/magic-link-requests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) });
    setSent(true);
  }
  return <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-6 p-6"><h1 className="text-3xl font-semibold">Entrar a Umbral</h1>{sent ? <p>Si la dirección está habilitada, recibirás un enlace para continuar.</p> : <form onSubmit={submit} className="flex flex-col gap-4"><label htmlFor="email">Email</label><input id="email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /><button type="submit">Enviar enlace</button></form>}</main>;
}
