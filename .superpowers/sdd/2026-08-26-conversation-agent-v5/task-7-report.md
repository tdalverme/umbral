# Task 7 Report — V5.4 Expressed Desires, Links, Revisions, and Withdrawals

## Implementation

Added `RecordDesireCommand`, `ReviseDesireCommand`, and `WithdrawDesireCommand`
to `contracts.py` and extended the closed `CommandV5` union. `ExecutedActV5`
now carries a `status: OutcomeStatusV5` field (default `applied`) so execution
results are self-describing; the radar executor was updated to set
`pending`/`rejected` explicitly for proposal and failure paths.

Extended `plan_turn_v5` in `policy.py`:
- `ExpressDesire` always yields an applied decision plus a
  `RecordDesireCommand` when evidence is valid; zero concept links is valid.
- `ReviseDesire`/`WithdrawDesire` require an authorized active desire ref.
  When `desire_ref` is absent, a single active desire is targeted; multiple
  active desires return `needs_clarification` with `desire.ambiguous` (never a
  guessed target); no active desire returns rejected `desire.not_active`.

Extended `EffectExecutorV5` in `executor.py` to route desire commands to the
existing `PreferenceServiceLike` methods using the expression UUIDs already in
the authorized refs: `record_expression` with `BindingDraft.unresolved(
"no_structured_evidence")` for zero concept links (preserving raw text and
subject ref), `revise_expression` with the previous expression id from the
`desire:` ref, and `withdraw_expression`. The subject key comes from the stable
`subject_ref` supplied by the command/context, never from an arbitrary slug.
Per the pre-flight ruling, the preference service has no native idempotency, so
the receipt `started/applied` guard is the service's responsibility (Task 9).

## RED

The focused suites failed at collection because the desire command union and
executor branches did not exist.

## GREEN

```text
$ pytest tests/unit/application/conversation/v5/test_policy_desires.py tests/unit/infrastructure/conversation/v5/test_desire_executor.py tests/unit/infrastructure/conversation/v5/test_radar_executor.py tests/unit/application/preferences -q
32 passed in 0.52s
```

One fixture span/offset mismatch was corrected on the first GREEN run.

## Verification

```text
$ pytest tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5 tests/unit/application/preferences -q
70 passed in 0.66s

$ ruff check src/umbral/application/conversation/v5 src/umbral/infrastructure/conversation/v5 tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5
All checks passed!

$ mypy src/umbral/application/conversation/v5 src/umbral/infrastructure/conversation/v5 tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5
Success: no issues found in 14 source files
```

## Files

- `src/umbral/application/conversation/v5/contracts.py` (desire commands, status)
- `src/umbral/application/conversation/v5/policy.py` (desire planning + ambiguity)
- `src/umbral/infrastructure/conversation/v5/executor.py` (preference adapters)
- `tests/unit/application/conversation/v5/test_policy_desires.py`
- `tests/unit/infrastructure/conversation/v5/test_desire_executor.py`

## Self-review

- Confirmed out-of-catalog desires persist with zero concept links and their
  exact raw text and subject ref.
- Confirmed ambiguous revisions return `needs_clarification` and never guess a
  target; missing/inactive desires are rejected with `desire.not_active`.
- Confirmed revisions/withdrawals use the authorized `desire:` expression UUID
  directly and hard force is never applied to semantic links.
- Confirmed the preference suite (32 tests) passes unchanged; no V4 production
  files were modified.

## Concerns

With concept links present, the executor records the desire with
`BindingDraft.unresolved("concept_link:<ref>")` drafts rather than inventing new
structured bindings: the V5 design treats concept linking as a separate
versioned result, and the links reference existing verified bindings preserved
in the interpretation/command trail. No new structured binding is fabricated
from model output.
