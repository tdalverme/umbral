export default function Page() {
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="mx-auto flex min-h-screen w-full max-w-3xl flex-col justify-center gap-8 px-6 py-16 outline-none sm:px-10"
    >
      <header className="flex flex-col gap-3">
        <p className="text-sm font-medium uppercase tracking-[0.18em] text-muted-foreground">
          Fundación del runtime
        </p>
        <h1 className="text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">Umbral</h1>
      </header>
      <section aria-labelledby="runtime-status-title" className="rounded-xl border border-border bg-card p-6 shadow-sm">
        <h2 id="runtime-status-title" className="text-lg font-semibold text-card-foreground">
          Estado del runtime
        </h2>
        <p className="mt-2 max-w-prose text-sm leading-6 text-muted-foreground">
          La aplicación está lista para recibir configuración del entorno.
        </p>
      </section>
    </main>
  );
}
