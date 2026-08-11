"""Ports for the agent runtime: run persistence, recorder and model gateway."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from umbral.application.agent.contracts import (
    GraphRun,
    ModelCall,
    ModelResult,
    NodeRun,
)


class GraphRunRepository(Protocol):
    def create(self, run: GraphRun) -> GraphRun | None: ...

    def get(self, run_id: UUID) -> GraphRun | None: ...

    def active_for_session(self, session_id: UUID) -> GraphRun | None: ...

    def mark(
        self,
        run_id: UUID,
        *,
        status: str | None = None,
        finished_at: datetime | None = None,
        latency_ms: int | None = None,
        token_usage: Mapping[str, object] | None = None,
        error_summary: Mapping[str, object] | None = None,
        attempt: int | None = None,
    ) -> GraphRun | None: ...


class NodeRunRepository(Protocol):
    def append(self, node_run: NodeRun) -> None: ...


class ModelCallRepository(Protocol):
    def append(self, call: ModelCall) -> None: ...


class RunRecorder(Protocol):
    def record_graph_run(self, run: GraphRun) -> GraphRun: ...

    def record_node_run(self, node_run: NodeRun) -> None: ...

    def record_model_call(self, call: ModelCall) -> None: ...


class ModelGateway(Protocol):
    def generate_structured(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        schema: Mapping[str, object],
        schema_version: str,
        prompt_version: str,
        model_version: str,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ModelResult: ...
