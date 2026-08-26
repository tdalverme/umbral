# Task 11 Report — V5 Eval Dataset, Production-path Executor, and Statistics

## Implementation

**Contracts.** Published `contracts/agent-evals/v4/`: `conversation-trajectories-v4.json` (+ closed `.schema.json`) with twelve cases covering the migrated V3 families and the required new V5 families (untrusted provenance, invalid refs, unsupported request, ambiguous revision, post-confirm refresh, partial multi-act, provider failure, reply fallback, idempotent retry, stale context, query never mutates, desire preservation); every case carries owner review metadata. `eval-policy-v4.json` defines trials; `graph-releases-v3.json` registers `graph-release-003` (V4 baseline, active) and `graph-release-005` (first V5 candidate, `gpt-4.1-mini`, `interpretation-v5`/`reply-v5`, V5 schemas/topology, activation pending).

**Loader.** `application/agent_evals/v4/loader.py` strictly parses dataset/policy/releases into frozen typed values; unknown invariants, missing fields, and missing files raise typed `EvalV4ValidationError`.

**Statistics.** `application/agent_evals/v4/statistics.py` exposes exact (unrounded) median success per family, run-to-run range, Wilson intervals per case (reusing the V3 interval), p50/p95 latency (nearest-rank), and cost summaries.

**Production-path executor.** `infrastructure/agent_evals/v4_flow.py` runs both fidelities through the **same** `build_graph_v5` (the `graph_factory` static attribute); the scripted adapter replaces only the interpreter seam (and can force provider/reply failures). Context assembly, deterministic policy, command execution, receipts, reply composition, and audit are unmodified production code. Durable services are backed by in-memory stores (`_EvalServices`: radar, chat, proposals, preferences, feedback, focus) so the suite runs without Postgres; the stale-context case exercises the V5 turn module's phase path with a genuinely stale snapshot. `compare_releases` labels identical-component releases as `statistical_replica`.

## RED

Contract tests failed because the dataset/loader did not exist; the same-path
suite failed at collection because `v4_flow.py` was missing.

## GREEN

The GREEN loop surfaced and fixed: `asdict` produces tuples (the graph's `_list`
needed tuple support), string lists needed a dedicated `_strings` helper, the
graph nodes must catch interpretation/policy failures into `failure_stage`, the
scripted reply call needed its own branch, `_is_provider_error` must accept
`provider.*` codes, the confirm evidence span was off by one, the stale case
needs a *new* filter to hit the optimistic-lock branch, and the idempotent
retry case replays the same `message_id`.

```text
$ pytest tests/contract/test_agent_evals_v4_contracts.py tests/unit/application/agent_evals/v4 tests/integration/agent_evals/test_v4_same_path.py tests/unit/application/conversation/v5 tests/unit/agent/test_graph_v5.py -q
80 passed in 11.12s
```

The scripted suite passes 12/12 cases through the production graph with zero
safety or quality failures.

## Verification

```text
$ ruff check src/umbral/application/agent_evals/v4 src/umbral/infrastructure/agent_evals/v4_flow.py tests/contract/test_agent_evals_v4_contracts.py tests/unit/application/agent_evals/v4 tests/integration/agent_evals/test_v4_same_path.py src/umbral/agent/graph_v5.py src/umbral/application/conversation/v5/service.py
All checks passed!

$ mypy src/umbral/application/agent_evals/v4 src/umbral/infrastructure/agent_evals/v4_flow.py tests/contract/test_agent_evals_v4_contracts.py tests/unit/application/agent_evals/v4 tests/integration/agent_evals/test_v4_same_path.py src/umbral/agent/graph_v5.py src/umbral/application/conversation/v5/service.py
Success: no issues found in 14 source files
```

## Files

- `contracts/agent-evals/v4/conversation-trajectories-v4.json` (+ schema)
- `contracts/agent-evals/v4/eval-policy-v4.json`
- `contracts/agent-evals/v4/graph-releases-v3.json`
- `src/umbral/application/agent_evals/v4/loader.py`
- `src/umbral/application/agent_evals/v4/statistics.py`
- `src/umbral/infrastructure/agent_evals/v4_flow.py`
- `tests/contract/test_agent_evals_v4_contracts.py`
- `tests/unit/application/agent_evals/v4/test_statistics.py`
- `tests/integration/agent_evals/test_v4_same_path.py`
- `src/umbral/agent/graph_v5.py` / `src/umbral/application/conversation/v5/service.py` (failure handling)

## Self-review

- Confirmed both fidelities share `build_graph_v5` and scripted output is
  adapted only at the interpreter seam.
- Confirmed the loader rejects a release whose declared component files are
  missing and every case carries owner review metadata.
- Confirmed identical-component releases are labeled `statistical_replica`.
- Confirmed the eval evidence retains stage attribution and no sensitive
  values.

## Concerns

The eval's durable services are in-memory implementations of the application
seams rather than Postgres repositories (the shared environment cannot run DB
integration reliably, per the baseline ruling); the V5 turn module, policy,
executor, receipts, graph, and reply are all the production classes. The
`graph-release-003` activation status is set to `active` in the V4 registry for
baseline continuity; the runtime selector in Task 12 keeps the production
default on the existing V4 path regardless.