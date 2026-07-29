# Contract: Durable Job Runtime

## Purpose

Define the application-facing Interface for at-least-once background work while
keeping job identity, state, retry and audit truth in PostgreSQL. RQ/Redis is an
Adapter and may be replaced without changing callers.

## Application Interface

```python
@dataclass(frozen=True)
class JobIdentity:
    job_type: str
    logical_target: str
    idempotency_key: str

@dataclass(frozen=True)
class SubmitJob:
    identity: JobIdentity
    correlation_id: UUID
    actor: AuditActor
    max_attempts: int

@dataclass(frozen=True)
class JobSnapshot:
    execution_id: UUID
    identity: JobIdentity
    state: JobState
    attempt_count: int
    max_attempts: int
    result: Mapping[str, JsonScalar] | None
    error_code: str | None

class JobRuntime(Protocol):
    def submit(self, command: SubmitJob) -> JobSnapshot: ...
    def get(self, execution_id: UUID) -> JobSnapshot: ...
```

`submit` is one deep operation: it validates the registered job type and
logical target, inserts or loads the durable execution, creates the outbox
message when necessary and returns the current snapshot.

## Identity and Replay

- Equality is exact equality of normalized `job_type`, `logical_target` and
  `idempotency_key`.
- Each job type owns deterministic logical-target normalization. A target is
  rejected if it is empty, unstable, secret-bearing or exceeds its bound.
- The first submission creates one execution and one initial outbox row.
- Concurrent duplicate submissions return the same execution.
- Replaying a terminal identity returns its stored state/result and creates no
  attempt, message or effect.
- Intentional reexecution requires a new idempotency key.
- Reusing a key under another job type or logical target creates an independent
  execution.

## Transport Interface

```python
class JobQueue(Protocol):
    def publish(
        self,
        *,
        execution_id: UUID,
        attempt_number: int,
        correlation_id: UUID,
    ) -> None: ...
```

Production uses RQ with JSON serialization. Test/local adapters are recording
or inline implementations. Transport payloads contain only the three fields
above; ORM objects, credentials, raw user input and pickle are forbidden.

## Handler Interface

```python
@dataclass(frozen=True)
class JobContext:
    execution_id: UUID
    attempt_number: int
    correlation_id: UUID
    release_id: str

class JobHandler(Protocol):
    job_type: str

    def normalize_target(self, raw_target: str) -> str: ...
    def run(self, context: JobContext) -> Mapping[str, JsonScalar]: ...
```

Handlers are registered explicitly. Dynamic module/function names supplied by
messages are forbidden.

## Failure Classification

- A handler raises `TransientJobError(code, retry_after=None)` only when the
  same identity can succeed later without changing input or invariants.
- A handler raises `PermanentJobError(code)` for validation, invariant,
  authorization or unsupported-operation failures.
- Unclassified exceptions are sanitized to `job.unclassified_failure`, become
  terminal and are reported to Sentry.
- Error code is persisted; exception message, arguments and traceback remain
  only inside the filtered error pipeline.
- A transient failure schedules another attempt only below `max_attempts`.
- Backoff is declared in the registered job definition and is bounded. The
  reference policy is five total attempts.

## Claim, Lease and Delivery Rules

1. A worker receives `(execution_id, attempt_number)`.
2. In one short transaction it locks the execution.
3. Terminal, future, mismatched-attempt or unexpired-running messages are
   acknowledged as no-ops.
4. A valid message increments the durable attempt count, creates an attempt
   row and sets a bounded lease.
5. The handler runs without an open claim transaction.
6. The worker commits normalized outcome and attempt state.
7. An expired lease becomes `abandoned`; the reaper schedules the next attempt
   or terminal failure.

Duplicate Redis deliveries are expected. PostgreSQL state determines whether
they may execute.

## Effect Guarantee

The queue is at-least-once. Each mutating handler MUST define its logical
effect guard:

- PostgreSQL-only effects commit effect and terminal job state in the same
  transaction and use a unique key derived from `execution_id`;
- an external provider receives its supported idempotency key and the
  resulting provider reference is recorded;
- immutable object writes use the object-version contract;
- a handler without a demonstrable guard may not be registered as mutating.

The reference job writes one uniquely constrained audit effect. Ten duplicate
submissions and duplicate deliveries must leave exactly one such row.

## Scheduler Contract

Supported schedule kinds are `one_shot` and `fixed_interval` with a minimum
60-second interval. The scheduler:

- stores and compares all instants in UTC;
- claims due rows with `FOR UPDATE SKIP LOCKED`;
- derives `schedule:<schedule_id>:<planned_at_utc>` as the occurrence key;
- advances/disables the schedule and submits the occurrence atomically;
- publishes through the same outbox;
- emits a heartbeat at least every 30 seconds.

Cron syntax, time-zone calendars, workflow graphs and user-visible scheduling
are outside this increment.

## Conformance Tests

Every `JobQueue` adapter and the composed runtime must prove:

1. one submission publishes one transport message;
2. ten same-identity submissions return one execution;
3. a terminal replay publishes nothing;
4. same key with different type or target remains independent;
5. duplicate delivery creates no concurrent duplicate attempt/effect;
6. transient failure follows declared bounded delays;
7. permanent and unclassified failures do not loop;
8. lost Redis state is rebuilt from unpublished/due PostgreSQL state;
9. an expired lease is recovered exactly once;
10. two schedulers create one occurrence;
11. payload serialization is JSON and contains only allowed IDs;
12. logs/traces contain allowed metadata only.
