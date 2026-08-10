"""In-memory agent fakes for unit tests."""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from umbral.application.agent.contracts import GraphRun, ModelCall, NodeRun


class RecordingRunRecorder:
    def __init__(self) -> None:
        self.runs: list[GraphRun] = []
        self.nodes: list[NodeRun] = []
        self.calls: list[ModelCall] = []

    def record_graph_run(self, run: GraphRun) -> GraphRun:
        self.runs.append(run)
        return run

    def record_node_run(self, node_run: NodeRun) -> None:
        self.nodes.append(node_run)

    def record_model_call(self, call: ModelCall) -> None:
        self.calls.append(call)

    def append(self, item: NodeRun | ModelCall) -> None:
        if isinstance(item, NodeRun):
            self.nodes.append(item)
        else:
            self.calls.append(item)


class InMemoryGraphRunRepository:
    _NON_TERMINAL = ("pending", "running", "interrupted")

    def __init__(self) -> None:
        self.runs: dict[UUID, GraphRun] = {}

    def create(self, run: GraphRun) -> GraphRun | None:
        if self.active_for_session(run.session_id) is not None:
            return None
        self.runs[run.run_id] = run
        return run

    def get(self, run_id: UUID) -> GraphRun | None:
        return self.runs.get(run_id)

    def active_for_session(self, session_id: UUID) -> GraphRun | None:
        for run in self.runs.values():
            if run.session_id == session_id and run.status in self._NON_TERMINAL:
                return run
        return None

    def mark(
        self,
        run_id: UUID,
        *,
        status: str | None = None,
        finished_at: object = None,
        latency_ms: int | None = None,
        token_usage: object = None,
        error_summary: object = None,
        attempt: int | None = None,
    ) -> GraphRun | None:
        current = self.runs.get(run_id)
        if current is None:
            return None
        updates = dict(asdict(current))
        if status is not None:
            updates["status"] = status
        if finished_at is not None:
            updates["finished_at"] = finished_at
        if latency_ms is not None:
            updates["latency_ms"] = latency_ms
        if token_usage is not None:
            updates["token_usage"] = token_usage
        if error_summary is not None:
            updates["error_summary"] = error_summary
        if attempt is not None:
            updates["attempt"] = attempt
        updated = GraphRun(**updates)
        self.runs[run_id] = updated
        return updated
