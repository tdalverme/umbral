import { cookies } from "next/headers";
import type { ReactElement } from "react";

import { CAPTURE_COOKIE, unsealCapture } from "@/lib/auth/cookies";
import { confirmCapture } from "./actions";

export default async function ConfirmPage(): Promise<ReactElement> {
  const store = await cookies();
  const valid = Boolean(unsealCapture(store.get(CAPTURE_COOKIE)?.value));
  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-6 p-6">
      <h1 className="text-3xl font-semibold">Continuar a Umbral</h1>
      <p>{valid ? "Confirmá para abrir tu sesión." : "El enlace ya no está disponible. Solicitá uno nuevo."}</p>
      {valid ? <form action={confirmCapture}><button className="rounded-md bg-primary px-4 py-2 text-primary-foreground" type="submit">Continuar a Umbral</button></form> : <a href="/login">Solicitar un enlace nuevo</a>}
    </main>
  );
}
