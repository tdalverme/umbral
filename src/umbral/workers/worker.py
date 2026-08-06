"""Worker claim/run/commit loop for queue messages."""

from __future__ import annotations

import os
from collections.abc import Mapping
from time import perf_counter
from typing import TYPE_CHECKING, Callable
from uuid import UUID

from rq import Worker
from rq.serializers import JSONSerializer

from umbral.application.jobs.contracts import JobContext, JsonScalar
from umbral.application.jobs.ports import JobRuntime
from umbral.application.runtime.telemetry import TelemetrySignal

if TYPE_CHECKING:
    from umbral.infrastructure.queue.rq_queue import RQJobQueue

Handler = Callable[[JobContext], Mapping[str, JsonScalar]]


class InMemoryWorker:
    def __init__(
        self,
        runtime: JobRuntime,
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


def build_rq_worker(queue: RQJobQueue) -> Worker:
    """Create the long-lived RQ worker with the sole durable queue contract.

    RQ's default worker forks on POSIX only; Windows hosts use the in-process
    ``SimpleWorker`` so local development can run the same durable queue.
    """

    worker_class = Worker
    if os.name == "nt":
        from rq.worker import SimpleWorker

        worker_class = SimpleWorker  # type: ignore[assignment]
    return worker_class(
        [queue.queue],
        connection=queue.queue.connection,
        serializer=JSONSerializer,
    )


def run_message(
    *,
    execution_id: str,
    attempt_number: int,
    correlation_id: str,
    worker: InMemoryWorker | None = None,
) -> bool:
    """Process one JSON-only RQ envelope through the explicit handler registry."""

    active_worker = worker
    if active_worker is None:
        from umbral.workers.composition import build_process_dependencies

        dependencies = build_process_dependencies()
        active_worker = InMemoryWorker(
            dependencies.runtime,
            dependencies.handlers,
            worker_id=dependencies.worker_id,
        )
    return active_worker.process(
        {
            "execution_id": execution_id,
            "attempt_number": attempt_number,
            "correlation_id": correlation_id,
        }
    )
