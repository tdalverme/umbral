import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentOpsView, type OpsOverview } from "./agent-ops-view";

const overview: OpsOverview = {
  latency_p95_ms: 1200,
  error_rate: 0.02,
  tool_success_rate: 0.98,
  interrupt_count: 3,
  tokens_total: 120000,
  cost_total_usd: 0.25,
  eval_regressions: [
    {
      eval_suite_id: "suite-1",
      candidate_release_id: "graph-release-002",
      blocked: true,
      reasons: ["agent_evals.undeclared_change:conversation-001"],
    },
  ],
  data_as_of: "2026-08-10T12:00:00.000Z",
};

describe("AgentOpsView", () => {
  it("renders the aggregate metrics read-only", () => {
    render(<AgentOpsView overview={overview} />);
    expect(screen.getByText("Latencia p95")).toBeDefined();
    expect(screen.getByText("1200 ms")).toBeDefined();
    expect(screen.getByText("2.0 %")).toBeDefined();
    expect(screen.getByText("98.0 %")).toBeDefined();
    expect(screen.getByText("USD 0.2500")).toBeDefined();
  });

  it("renders the data freshness timestamp", () => {
    render(<AgentOpsView overview={overview} />);
    expect(screen.getByTestId("data-as-of").textContent).toContain("datos al");
  });

  it("shows eval regressions linked to their release", () => {
    render(<AgentOpsView overview={overview} />);
    expect(screen.getByText(/candidata graph-release-002/)).toBeDefined();
    expect(screen.getByText("agent_evals.undeclared_change:conversation-001")).toBeDefined();
  });

  it("offers no mutation actions", () => {
    render(<AgentOpsView overview={overview} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
