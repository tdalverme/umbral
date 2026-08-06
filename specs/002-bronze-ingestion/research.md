# Research: Bronze Ingestion

**Feature**: `002-bronze-ingestion` | **Date**: 2026-08-06

Decisions, rationale and rejected alternatives for the design in
[plan.md](./plan.md). Format per decision: Decision / Rationale / Alternatives
considered.

## R-001 ImportSource placement and shape

- **Decision**: `ImportSource` is an application-layer port living in
  `application/ingestion/ports.py`, next to the raw contracts. The production
  adapter is `FileImportSource` (reads CSV/JSON bytes and yields
  `RawRecord` values); a `FakeImportSource` (or in-memory variant) provides the
  same observable behavior for tests.
- **Rationale**: The codebase already models external seams this way
  (`JobQueue`, `ObjectStore` in `application/*/ports.py`), keeping domain and
  application free of I/O and framework imports while infrastructure supplies
  adapters. The port receives a batch, source identity and version, and returns
  snapshots plus an ingestion report — it never mentions Silver, satisfying the
  backlog constraint and the dependency direction.
- **Alternatives considered**:
  - A pure domain interface in `domain/`. Rejected: the existing convention
    keeps adapters-to-be on the application boundary and domain files purely
    value-based; a protocol with I/O semantics fits the application seam.
  - A single service class performing both reading and persistence. Rejected:
    it would couple the source format to repositories and block testing the
    validator and idempotency independently.

## R-002 Import contract v1 (prerequisite UM-H0-009)

- **Decision**: This increment ships a minimal controlled-beta import contract
  v1 under `contracts/import/v1/` (see
  [import-contract-v1.md](./contracts/import-contract-v1.md)): JSON envelope or
  CSV, UTF-8, bounded file size, declared `source_id` / `source_version` /
  `contract_version`, and a small required-field set for residential rental
  listings in CABA. UM-H0-009 is a H0 prerequisite that is not yet published;
  the plan treats drafting this v1 as part of the increment so that validation
  is machine-checkable, and ratifies it against the real controlled source
  before beta.
- **Rationale**: FR-004 requires rejecting unsupported formats, encodings,
  sizes and versions with actionable diagnostics. Without a concrete published
  contract there is nothing to validate against; a minimal v1 is the smallest
  artifact that closes that loop and keeps the spec's dependency documented.
- **Alternatives considered**:
  - Block this increment until UM-H0-009 is published. Rejected: it stalls the
    whole data path; the plan instead consumes the best-available contract and
    keeps the loader versioned so a later ratified contract swaps in without
    domain changes.
  - Define the contract only in prose in the spec. Rejected: not machine
    checkable, so validation could not be a deterministic test.

## R-003 Batch and record idempotency

- **Decision**: Two layers of idempotency.
  1. Batch: reuse the durable job identity `(job_type, logical_target,
     idempotency_key)`. `job_type="ingestion.import_batch"`,
     `logical_target=<source_id>:<batch_key>`,
     `idempotency_key=<batch_key>`. If the operator does not supply a
     `batch_key`, the API derives it as the SHA-256 of the uploaded file, so an
     identical re-upload reuses the same run. A terminal replay returns the
     existing result with zero new effects.
  2. Record: a unique constraint on `(source_id, external_id, content_sha256)`
     on `raw_listing_snapshots` prevents identical records from being inserted
     twice even across different batch keys.
- **Rationale**: Both layers are cheap and close the cases in the spec
  (US2.1-US2.3): same key/hash re-import, same content different key, and an
  interrupted import retried with the same identity. Run counts are derived at
  completion from the actually committed rows (never accumulated), so retries
  cannot double count.
- **Alternatives considered**:
  - Only batch-level idempotency. Rejected: an interrupted run that partially
    committed could leave partial rows on a crashed submit; record-level
    uniqueness closes that hole.
  - Hash-only identity without the job runtime. Rejected: we would reimplement
    leases, retries and terminal replay that `JobRuntime` already provides.

## R-004 Raw content preservation

- **Decision**: The full uploaded raw file is written as one immutable object
  version (`purpose="ingestion.raw_batch"`) through the existing
  `VersionedObjects` seam before any transformation, giving full-fidelity
  audit/reparse content. The Bronze `raw_listing_snapshots` row stores the
  parsed per-record payload (JSONB), `content_sha256`, source/version,
  timestamps and a reference to the run. Heavy media bytes are NOT downloaded
  in this increment; media URLs remain strings in the payload.
- **Rationale**: Satisfies FR-010/FR-011 and the backlog's "preservar raw
  listing snapshots inmutables … antes de transformar" while reusing the
  verified immutable object contract instead of inventing a new store. Download
  of media belongs to enrichment (H2.2+), not capture.
- **Alternatives considered**:
  - Store the whole raw file bytes in Postgres. Rejected: violates the
    object-storage boundary and bloats Bronze.
  - Download and store media blobs now. Rejected: speculative scope; the
    controlled source already supplies URLs and enrichment is a later epic.

## R-005 Duplicates and quarantine semantics

- **Decision**: A record identical to one already present for the same source
  and `external_id` within the batch is counted as a duplicate and stored once
  (never quarantined). A record that fails contract validation is quarantined
  with a stable `code`, `rule`, actionable `detail` and a bounded payload
  reference. Records with the same `external_id` but changed content create a
  new snapshot row (additive), leaving versioning/change detection to H2.2.
- **Rationale**: Matches the spec's edge cases (invalid records isolate without
  aborting the batch; duplicates are reported, not rejected) and keeps H2.1
  additive so later epics can detect changes between observations.
- **Alternatives considered**:
  - Quarantine duplicates too. Rejected: identical content is not an error; it
    is the idempotent case and must show up in the accepted/duplicate counts.
  - Reject the whole batch when one record fails. Rejected: explicitly
    contradicts the per-record quarantine requirement and the backlog's failure
    philosophy.

## R-006 Operator entry authorization

- **Decision**: New deny-by-default actions in `domain/identity/policy.py`:
  `ops.ingestion.batch.submit`, `ops.ingestion.run.read` and
  `ops.ingestion.quality.read`, each allowed only for `operator` and
  `administrator`. The API router uses the existing `AccessControl.authorize`
  with the product session token. Because the identity increment is already in
  the tree, the operator role is available; the entry is bound to it now, so no
  environment-level backdoor is needed. Upload accepts a file only — never
  arbitrary URLs (FR-021).
- **Rationale**: Conforms to the spec clarification and to deny-by-default
  testing (SC-007, SC-008). Reuses `AccessControl` instead of introducing a
  parallel authorization path.
- **Alternatives considered**:
  - Restrict via Cloudflare/environment controls only. Rejected: product
    identity exists and the operator role is the correct, auditable boundary.
  - Allow anonymous local dev access. Rejected: would create a security
    backdoor and contradict the accepted clarification.

## R-007 Quality report contents

- **Decision**: `GET /api/v1/imports/runs/{run_id}/quality` returns
  accepted / quarantined / duplicate / missing-field counts plus per-field
  missing counts and flagged abnormal distributions (price, surface, rooms) for
  the batch. A CSV download surfaces per-record quarantine detail. Both respect
  operator authorization and the report is derived from committed rows, so it
  always matches real counts (SC-006).
- **Rationale**: Minimal, auditable and consistent with the spec; everything is
  deterministic and versioned by run.
- **Alternatives considered**:
  - A dashboard surface in the web app. Rejected: H2.1's operator entry is an
    API; dashboards belong to the operator console (H6.3).

## R-008 Execution topology

- **Decision**: Upload → API persists `import_runs` (pending) and submits the
  durable job; the worker handler performs validation, object write and
  snapshot/quarantine insertion inside the run, updating counts and state.
  Readiness adds no new critical dependency (Postgres and object storage are
  already critical to the worker surface).
- **Rationale**: Reuses the at-least-once job runtime (outbox, leases, bounded
  retries) so interrupted imports recover without duplicating records. Progress
  is read from the run's committed state and counts.
- **Alternatives considered**:
  - Synchronous import inside the API request. Rejected: large batches would
    exceed request bounds and lose restartability; the durable runtime exists
    precisely for this.
