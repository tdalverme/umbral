"""Worker claim/run/commit loop for queue messages."""

from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter
from typing import Callable
from uuid import UUID

from umbral.application.jobs.contracts import JobContext, JsonScalar
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.application.runtime.telemetry import TelemetrySignal

Handler = Callable[[JobContext], Mapping[str, JsonScalar]]


class InMemoryWorker:
    def __init__(
        self,
        runtime: InMemoryJobRuntime,
        handlers: Mapping[str, Handler | object],
        *,
        worker_id: str,
    ) -> None:
        self.runtime = runtime
        self.handlers = handlers
        self.worker_id = worker_id
        self.signals: list[TelemetrySignal] = []

    def process(self, message: object) -> bool:
        payload = getattr(message, "payload", message)
        if not isinstance(payload, Mapping):
            raise ValueError("queue message payload must be an object")
        execution_id = UUID(str(payload["execution_id"]))
        attempt_number = int(payload["attempt_number"])
        correlation_id = UUID(str(payload["correlation_id"]))
        if correlation_id != self.runtime.correlation_id(execution_id):
            return False
        claim = self.runtime.claim(
            execution_id=execution_id,
            attempt_number=attempt_number,
            worker_id=self.worker_id,
        )
        if claim is None:
            return False
        started = perf_counter()
        identity = self.runtime.identity(execution_id)
        handler = self.handlers.get(identity.job_type)
        if handler is None:
            from umbral.application.jobs.contracts import PermanentJobError

            self.runtime.record_outcome(
                claim, PermanentJobError("job.handler_not_registered")
            )
            return True
        try:
            if callable(handler):
                result = handler(claim.context)
            else:
                run = getattr(handler, "run", None)
                if not callable(run):
                    raise TypeError("registered handler is not callable")
                result = run(claim.context)
        except Exception as error:
            self.runtime.record_outcome(claim, error)
        else:
            self.runtime.record_outcome(claim, result)
        snapshot = self.runtime.get(execution_id)
        self.signals.append(
            TelemetrySignal(
                correlation_id=str(claim.context.correlation_id),
                service_name="worker",
                environment="local",
                release_id=claim.context.release_id,
                operation="job.execute",
                state=str(snapshot.state),
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
                job_type=identity.job_type,
                job_state=str(snapshot.state),
                attempt_number=attempt_number,
            )
        )
        return True


def run_message(
    *,
    execution_id: str,
    attempt_number: int,
    correlation_id: str,
) -> None:
    """RQ entrypoint placeholder; composition injects the process runtime."""

    del execution_id, attempt_number, correlation_id
