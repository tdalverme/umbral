# Conversation Agent V5 Design

**Date:** 2026-08-26

**Status:** Approved in design review

## Purpose

Redesign Umbral's conversational agent as V5 so it can convert user intent into
correct, safe, auditable product effects. V5 runs in parallel with V4 until it
passes its release gates. The first V5 releases keep `gpt-4.1-mini` fixed so
architecture and model quality can be measured independently; model selection
is a later experiment.

V5 must support the complete conversational surface: queries, safe refusals,
radar creation and refinement, expressed desires both inside and outside the
computable catalog, corrections and withdrawals, contextual listing feedback,
confirmations, and ordered multi-act turns.

## Non-goals

- The LLM does not choose final ranking, scores, hard filters, or notifications.
- V5 does not give the agent free SQL or unrestricted database access.
- V5 does not silently migrate, refactor, or change V4 behavior.
- The initial V5 work does not compare or adopt a model other than
  `gpt-4.1-mini`.
- V5 does not make qualitative concepts hard or let learning elevate them to
  hard.

## Release Strategy

V4 remains available as the baseline and rollback path. V5 receives new,
versioned contracts for context, interpretation, state, prompts, topology, and
release metadata. Shared application modules may be reused through existing
interfaces, but V5 behavior must not be introduced into V4 through conditional
branches.

The redesign is delivered in vertical releases:

1. **V5.0 — evidence:** reproducible baseline and stage-attributed reports.
2. **V5.1 — contracts:** authorized context and discriminated acts.
3. **V5.2 — safe read path:** queries, unsupported requests, and untrusted
   content handling.
4. **V5.3 — radar mutation:** radar creation and filter refinement.
5. **V5.4 — desires:** expressed desires, concept links, revisions, and
   withdrawals.
6. **V5.5 — feedback:** feedback tied to verified listing context.
7. **V5.6 — orchestration:** confirmation and ordered multi-act execution.
8. **V5.7 — release:** effect-grounded replies, hardening, performance, and
   activation gates.

Each release must produce independently testable, integrated behavior from
interpretation through persisted evidence. A release ID whose components are
identical to another release is a statistical replica, not a functional
candidate.

## Architecture

The external seam is a single deep module, `ConversationTurnV5`: process one
turn against an authorized snapshot and return a complete, auditable result.
Its implementation contains five internal modules:

```text
UI / Product API
       |
       v
ConversationTurnV5
       |
       +-- ContextAssemblerV5
       +-- IntentInterpreterV5
       +-- TurnPolicyV5
       +-- EffectExecutorV5
       +-- ReplyComposerV5
```

### ContextAssemblerV5

Produces an immutable, minimal snapshot of data the user is authorized to
reference during this turn. It reads through application/domain ports and does
not expose repositories or query facilities to the model.

### IntentInterpreterV5

Maps the user's message plus authorized context to an ordered list of typed
acts. It proposes intent only: it neither authorizes acts nor produces durable
effects. Managed and scripted adapters occupy this seam because both are real
variants used by production and deterministic tests.

### TurnPolicyV5

Pure, deterministic module that validates evidence, references, ordering,
materiality, and confirmation requirements. It returns an execution plan with
explicit decisions and reason codes.

### EffectExecutorV5

Executes authorized commands through explicit application interfaces. It has no
free database or tool access. Each command is atomic and idempotent, and checks
the versions on which its plan was based.

### ReplyComposerV5

Composes user-visible output from actual plan decisions, effects, pending
actions, and failures. It must not claim an effect merely because the
interpreter proposed it.

## Authorized Turn Context

`TurnContextV5` contains only:

- user and session identifiers;
- active radar identifier and version;
- current hard filters and their strength;
- active expressed desires and their stable references;
- current concept links and computable preferences;
- the active pending action, if any;
- focused entity and verified listing identifiers;
- capabilities allowed in the current product surface;
- external or quoted content marked explicitly as untrusted;
- a context schema version and correlation identifier.

The context must distinguish user-authored instructions from listing text,
documents, retrieved evidence, and other untrusted content. An entity reference
is usable only if the assembler included it in the snapshot.

## Interpretation Contract

`TurnInterpretationV5` is an ordered collection of discriminated acts. It does
not contain an open `payload: dict`. The initial vocabulary is:

- `CreateRadar`
- `SetFilter`
- `ClearFilter`
- `ExpressDesire`
- `ReviseDesire`
- `WithdrawDesire`
- `RecordFeedback`
- `ResolvePending`
- `Query`
- `UnsupportedRequest`

Each variant defines required fields and forbids unrelated fields. Object
references use stable references from `TurnContextV5`; model-produced arbitrary
UUIDs are invalid. The schema must reject incomplete acts before policy
planning.

An interpretation also records model version, prompt version, schema version,
confidence, and evidence spans from the user's message. Confidence is evidence
for review and clarification; it never grants authority.

## Expressed Desires and Concepts

V5 preserves an authorized expressed desire even when Umbral cannot evaluate
it. `ExpressDesire` stores the original text and a stable subject reference.
Concept linking is a separate, versioned result containing zero or more concept
references, confidence, evidence, and limitations.

No concept match is a valid outcome. It contributes no score until supported by
an observable concept, but the desire remains part of the radar. A semantic or
qualitative concept remains soft. Neither the interpreter nor learning can
create or supersede a hard filter.

Revision and withdrawal refer to an active desire in the authorized context.
When the target is ambiguous, policy returns clarification rather than choosing
one silently.

## Policy Decisions

Each planned act has exactly one decision:

- `applied`: authorized and successfully executed;
- `pending`: valid, material, and awaiting confirmation;
- `rejected`: prohibited, inconsistent, or unsupported;
- `needs_clarification`: a user decision or reference is missing.

The policy enforces these invariants:

1. A mutation requires explicit evidence in the user's message.
2. Untrusted content cannot originate an act or supply mutation evidence.
3. Object references must exist in the authorized context.
4. `Query` cannot produce durable product mutations.
5. Unsupported operations remain `UnsupportedRequest`; they are never
   approximated as another mutation.
6. Material changes create a pending proposal and do not alter durable state
   before confirmation.
7. Qualitative concepts cannot be hard.
8. Ranking, scoring, and notification decisions remain outside the agent.
9. A provider or contract failure produces no durable effect.
10. A stale context version prevents execution against changed state.

## Multi-act Semantics

The full interpretation is schema- and reference-validated before execution.
Processing then occurs in ordered segments:

1. Resolve, reject, or edit the active pending action first.
2. Reload context if that decision changes durable state.
3. Revalidate subsequent acts against the refreshed context.
4. Execute safe acts in expressed order.
5. Stop the affected segment at a pending or clarification decision.
6. Mark later acts as not executed when their prerequisites were not met.

There is no global transaction covering an entire conversational turn. An
earlier independent safe act may remain applied when a later act needs
clarification. Each act is atomic and idempotent, and its ordering and outcome
are persisted. The reply distinguishes applied, pending, rejected, clarified,
and unexecuted acts.

## Failure Handling

Failures are typed and attributed to one stage:

- `context_failure`
- `interpretation_failure`
- `policy_failure`
- `execution_failure`
- `reply_failure`
- `provider_failure`
- `contract_or_fixture_failure`

Provider and interpretation failures execute nothing and return a recoverable
response. Policy rejects invalid or unauthorized acts with stable reason codes.
Execution version conflicts return clarification/retry rather than applying a
stale plan. Reply failures do not erase the persisted execution record and must
fall back to a deterministic effect summary.

## Audit Evidence

Every turn persists or emits traceable evidence for:

- input message identity and correlation ID;
- authorized context version and relevant object versions;
- prompt, model, interpretation schema, policy, and topology versions;
- structured interpretation and evidence spans;
- plan decisions and reason codes;
- idempotency keys and actual effects;
- state before and after, represented by safe snapshots or hashes;
- pending actions and unresolved acts;
- final user-visible response and any fallback path.

Sensitive data and secrets must not be copied into eval artifacts. Listing text
is retained only to the extent required by existing evidence and privacy
policies and remains marked untrusted.

## Evaluation Design

V5 uses three test levels:

1. Unit tests for context assembly, discriminated schemas, pure policy,
   multi-act ordering, version conflicts, and effect-grounded replies.
2. Scripted trajectories that traverse the production V5 path with a
   deterministic interpreter adapter.
3. Managed evals using `gpt-4.1-mini`, repeated enough to expose run-to-run
   variance and compared against the unchanged V4 baseline.

Each trial report includes the authorized context, structured interpretation,
plan, reason codes, effects, state transition, response, cost, latency, and
failure stage. Reports provide representative samples for each failure family.
Baseline replicas are summarized as distributions; a single stochastic delta
is not treated as a product improvement.

The existing V3 trajectories are migrated where semantics remain valid. New
cases cover untrusted-content provenance, invalid references, unsupported
requests, ambiguous desire revisions, context refresh between acts, partial
multi-act execution, provider failure, reply fallback, idempotent retries, and
version conflicts.

## Activation Gates

V5 may replace V4 only when the same registered release satisfies all gates:

- 100% of critical safety invariants across every managed run;
- 100% for `query-never-mutates`;
- at least 90% success for radar creation/refinement, desires, feedback,
  correction, and multi-act families;
- at least 95% success across regression trajectories;
- zero schema-invalid acts reaching policy planning;
- zero accepted references absent from authorized context;
- less than five percentage points of run-to-run variation for each relevant
  family;
- no material cost regression against the V4 baseline;
- managed p95 latency below five seconds per turn, unless the owner records a
  time-bounded exception before activation.

Activation records the approving owner and evidence directory. Rollback selects
V4 without rewriting V4 data or behavior. Compatibility and migration of any
new persisted V5 records must be verified before activation.

## Post-V5 Model Evaluation

After V5 passes with `gpt-4.1-mini`, model benchmarking becomes a separate
experiment. Every candidate keeps context, prompt, schema, topology, policy, and
price table fixed and changes only `model_version`. Candidates are compared on
the same safety, capability, regression, variance, latency, and cost dimensions;
no model is adopted if it weakens a critical safety gate.

