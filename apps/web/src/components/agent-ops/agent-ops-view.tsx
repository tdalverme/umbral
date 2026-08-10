"use client";

import type { ReactNode } from "react";

export interface OpsOverview {
  latency_p95_ms: number;
  error_rate: number;
  tool_success_rate: number;
  interrupt_count: number;
  tokens_total: number;
  cost_total_usd: number;
  eval_regressions: Array<{
    eval_suite_id: string;
    candidate_release_id: string | null;
    blocked: boolean;
    reasons: string[];
  }>;
  data_as_of: string;
}

export function AgentOpsView({ overview }: { overview: OpsOverview }): ReactNode {
  const asOf = new Date(overview.data_as_of);
  return (
    <main className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1>Operación del agente</h1>
        <p data-testid="data-as-of">Vista interna de solo lectura · datos al {asOf.toLocaleString()}</p>
      </header>
      <section className="grid grid-cols-2 gap-4 md:grid-cols-3" aria-label="Métricas del agente">
        <MetricCard label="Latencia p95" value={`${overview.latency_p95_ms} ms`} />
        <MetricCard label="Tasa de error" value={`${(overview.error_rate * 100).toFixed(1)} %`} />
        <MetricCard label="Tool success" value={`${(overview.tool_success_rate * 100).toFixed(1)} %`} />
        <MetricCard label="Interrupciones" value={String(overview.interrupt_count)} />
        <MetricCard label="Tokens totales" value={overview.tokens_total.toLocaleString()} />
        <MetricCard label="Costo total" value={`USD ${overview.cost_total_usd.toFixed(4)}`} />
      </section>
      <section aria-label="Regresiones de eval">
        <h2>Regresiones de eval</h2>
        {overview.eval_regressions.length === 0 ? (
          <p>Sin regresiones bloqueadas.</p>
        ) : (
          <ul>
            {overview.eval_regressions.map((regression) => (
              <li key={regression.eval_suite_id}>
                <span>Suite {regression.eval_suite_id}</span>
                {regression.candidate_release_id ? ` · candidata ${regression.candidate_release_id}` : ""}
                <ul>
                  {regression.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

function MetricCard({ label, value }: { label: string; value: string }): ReactNode {
  return (
    <div>
      <p>{label}</p>
      <p>{value}</p>
    </div>
  );
}
