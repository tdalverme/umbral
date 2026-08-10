"""Idempotent run/node/model-call recording with 0 PII (UM-H4-006)."""

from __future__ import annotations

from umbral.application.agent.contracts import GraphRun, ModelCall, NodeRun
from umbral.application.agent.ports import (
    GraphRunRepository,
    ModelCallRepository,
    NodeRunRepository,
)


class RunRecorderService:
    """Records runs and their executions; summaries never carry content."""

    def __init__(
        self,
        *,
        graph_runs: GraphRunRepository,
        node_runs: NodeRunRepository,
        model_calls: ModelCallRepository,
    ) -> None:
        self.graph_runs = graph_runs
        self.node_runs = node_runs
        self.model_calls = model_calls

    def record_graph_run(self, run: GraphRun) -> GraphRun:
        persisted = self.graph_runs.create(run)
        if persisted is None:
            # A concurrent non-terminal run already exists for the session.
            return run
        return persisted

    def record_node_run(self, node_run: NodeRun) -> None:
        self.node_runs.append(node_run)

    def record_model_call(self, call: ModelCall) -> None:
        self.model_calls.append(call)
