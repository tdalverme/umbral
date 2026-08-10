"""Run recorder unit tests (US5, SC-006)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from tests.support.agent import InMemoryGraphRunRepository, RecordingRunRecorder

from umbral.application.agent.contracts import GraphRun, ModelCall, NodeRun
from umbral.application.agent.service import RunRecorderService

_NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _recorder() -> tuple[
    RunRecorderService, InMemoryGraphRunRepository, RecordingRunRecorder
]:
    repo = InMemoryGraphRunRepository()
    recording = RecordingRunRecorder()
    service = RunRecorderService(
        graph_runs=repo,
        node_runs=recording,
        model_calls=recording,
    )
    return service, repo, recording


def test_record_graph_run_is_idempotent_on_conflict() -> None:
    service, repo, _recording = _recorder()
    run = GraphRun(
        run_id=uuid4(),
        session_id=uuid4(),
        state_schema_version=1,
        topology_version=1,
        status="running",
        attempt=1,
        correlation_id=uuid4(),
        started_at=_NOW,
    )
    assert service.record_graph_run(run) is run
    assert repo.get(run.run_id) is not None
    # A second run for the same session conflicts and returns the input untouched.
    duplicate = GraphRun(
        run_id=uuid4(),
        session_id=run.session_id,
        state_schema_version=1,
        topology_version=1,
        status="running",
        attempt=1,
        correlation_id=uuid4(),
        started_at=_NOW,
    )
    assert service.record_graph_run(duplicate) is duplicate
    assert repo.get(duplicate.run_id) is None


def test_records_node_and_model_calls_without_content() -> None:
    service, _repo, recording = _recorder()
    run_id = uuid4()
    correlation_id = uuid4()
    service.record_node_run(
        NodeRun(
            node_run_id=uuid4(),
            graph_run_id=run_id,
            node_name="generate_reply",
            node_kind="node",
            status="completed",
            correlation_id=correlation_id,
            started_at=_NOW,
            finished_at=_NOW,
        )
    )
    service.record_model_call(
        ModelCall(
            call_id=uuid4(),
            graph_run_id=run_id,
            model_version="m1",
            prompt_version="p1",
            schema_version="reply-v1",
            status="success",
            correlation_id=correlation_id,
            input_tokens=1,
            output_tokens=2,
            total_tokens=3,
            latency_ms=5,
        )
    )
    assert len(recording.nodes) == 1
    assert len(recording.calls) == 1
    assert recording.nodes[0].node_name == "generate_reply"
    assert recording.calls[0].total_tokens == 3
