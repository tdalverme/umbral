import { forwardRadarRequest } from "@/lib/radar/server";

import { AgentOpsView, type OpsOverview } from "@/components/agent-ops/agent-ops-view";

export const metadata = { title: "Operación del agente" };

export default async function AgentOpsPage(): Promise<React.ReactNode> {
  const response = await forwardRadarRequest("/api/v1/agent/ops/overview", {});
  if (!response.ok) {
    return <p className="p-6 text-sm text-destructive">No se pudo cargar la vista operativa del agente.</p>;
  }
  const overview = (await response.json()) as OpsOverview;
  return <AgentOpsView overview={overview} />;
}
