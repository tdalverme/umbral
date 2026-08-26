# Task 12 Report — Release Gates, Runtime Selection, and Operational Runbook

## Implementation

**Gate.** Added `application/agent_evals/v4/gate.py` with
`evaluate_v5_gate(report, latency_exception=None) -> GateDecisionV5`. Strict
thresholds: critical safety and query `== 1.0`, core families `>= 0.90`,
regression `>= 0.95`, run-to-run variation `< 5.0` pp, p95 latency `< 5000` ms,
invalid planned acts and unauthorized refs `== 0`, and no material cost
regression. Every failed reason is returned in deterministic order. A
time-bounded `LatencyExceptionV5` (owner, rationale, expiry, evidence ref) can
waive only the latency gate and must be unexpired; it can never waive safety,
authorization, schema, capability, or regression gates.

**Runtime selection.** `infrastructure/agent/production.py` gained
`select_production_conversation_builder(settings)`: `graph-release-003` (and the
other V4 ids) select the existing `build_production_copilot_stack`; `graph-release-005`
selects the new `build_production_v5_stack` (V5 graph over the real services,
SQLAlchemy receipts, Postgres checkpointer, managed/fake gateway, no-op focus
reader); any unknown release fails closed; V5 without registered activation
evidence (`AGENT_V5_ACTIVATION_EVIDENCE`) fails closed. `build_production_conversation_stack`
dispatches through the selector. `settings.py` added the
`agent_v5_activation_evidence` field + env var. V4 composition is untouched;
the default release keeps the V4 path.

**Runbook.** `docs/runbooks/agent-v5-release.md` documents prerequisite
checks, scripted suite, repeated managed suite, evidence review, the gate
command, owner approval record, release-setting change, smoke test, rollback to
`graph-release-003`, post-rollback verification, and the later model benchmark
as a separate release comparison changing only `model_version`.

**Harness.** `scripts/check.ps1` gained an inline "Conversation V5" check
(running the V5 contract/unit suites) without removing existing checks and
without a new wrapper script.

## RED

The gate and selector tests failed because neither existed.

## GREEN

```text
$ pytest tests/unit/application/agent_evals/v4 tests/unit/infrastructure/agent/test_production_v5.py tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5 tests/unit/agent tests/unit/config tests/contract/test_agent_contracts_v5.py tests/contract/test_agent_evals_v4_contracts.py tests/integration/agent_evals/test_v4_same_path.py -q
287 passed in 3.10s
```

Plus V4 agent/evals regression (32 passed) and the earlier V4 graph suites.

## Verification

```text
$ ruff check src/umbral/application/agent_evals/v4/gate.py src/umbral/infrastructure/agent/production.py src/umbral/infrastructure/config/settings.py tests/unit/application/agent_evals/v4/test_gate.py tests/unit/infrastructure/agent/test_production_v5.py
All checks passed!

$ mypy src/umbral/application/agent_evals/v4/gate.py src/umbral/infrastructure/agent/production.py src/umbral/infrastructure/config/settings.py tests/unit/application/agent_evals/v4/test_gate.py tests/unit/infrastructure/agent/test_production_v5.py
Success: no issues found in 5 source files
```

## Files

- `src/umbral/application/agent_evals/v4/gate.py`
- `tests/unit/application/agent_evals/v4/test_gate.py`
- `src/umbral/infrastructure/agent/production.py` (selector + V5 stack)
- `src/umbral/infrastructure/config/settings.py`
- `tests/unit/infrastructure/agent/test_production_v5.py`
- `docs/runbooks/agent-v5-release.md`
- `scripts/check.ps1`

## Self-review

- Confirmed the gate returns every failed reason deterministically and the
  latency exception is explicit, time-bounded, and never waives safety or
  authorization gates.
- Confirmed V4 releases select the existing copilot builder, V5 requires
  registered activation evidence, and unknown releases fail closed.
- Confirmed the default release and V4 composition remain unchanged; no V4
  graph files were touched.

## Concerns

The full `pytest` / `./scripts/check.ps1` run includes DB/provider integration
suites that cannot pass in this shared environment (baseline ruling); the
scoped V5 suites plus V4 regressions all pass. The managed eval suite and the
scripted comparison run are documented in the runbook and remain owner-gated.
`npm run build` has no frontend to run; the runbook records that gap instead of
creating a placeholder.