# Agent Evals v3 — solo-owner operating workflow

The v3 harness replaces the active conversational eval path: one canonical
24-case dataset (`conversation-trajectories-v3`), deterministic scripted
grading in CI, and an opt-in managed flow for prompt/model release
candidates. V1/v2 contracts remain frozen, readable and conformance-tested;
nothing in this workflow edits a prior release entry.

## Principles

- CI runs only the scripted adapter, one trial per case, no provider
  network and no provider credentials.
- Managed quality metrics are advisory; only deterministic safety and
  contract failures block automatically.
- Prompt/model releases require a complete real-provider report plus
  explicit owner approval (`approved_by: tomi`).
- Normal managed cases run 3 trials; `risk: critical` cases run 10; the
  values come only from `eval-policy-v3.json`.
- Provider failures get at most one fresh isolated retry; incomplete or
  budget-exhausted suites cannot support approval.
- Reports contain sanitized inputs, structured traces, state diffs and
  refs — never chain-of-thought or secrets.

## Workflows

### 1. After deterministic code changes

Run the dedicated harness:

```powershell
.\scripts\check-evals.ps1
```

It registers the v1/v2 conformance suites and every v3 test (contracts,
grading, adapters, executor over the full dataset, same-path proof,
comparison, reporting, flow, architecture boundaries). Expected
`[PASS]`.

### 2. Local managed iteration without holdout

While iterating locally, run a development-only managed suite through the
Python module (no release evidence, no approval step):

```powershell
$env:PYTHONPATH = "src"
python -m umbral.infrastructure.agent_evals.v3_flow `
  --baseline graph-release-003 `
  --candidate graph-release-003 `
  --cost-cap-usd 5 `
  --no-holdout
```

Requires `AGENT_MODEL_PROVIDER=managed`, `AGENT_MANAGED_ENDPOINT`,
`AGENT_MANAGED_API_KEY`, `AGENT_MODEL_NAME` and the usual infrastructure
settings (`DATABASE_URL`, etc.), and a running Postgres at head.

### 3. Release candidate run

Bootstrap the baseline by running the same release in both slots, then run
each candidate against it:

```powershell
.\scripts\run-agent-evals.ps1 `
  -Baseline graph-release-003 `
  -Candidate graph-release-003 `
  -CostCapUsd 5
```

and later

```powershell
.\scripts\run-agent-evals.ps1 `
  -Baseline graph-release-003 `
  -Candidate graph-release-004 `
  -CostCapUsd 5
```

Exit codes: `0` complete/advisory, `2` safety blocked, `3` incomplete,
`4` invalid configuration. Evidence is written for every outcome under
`docs/runbooks/evidence/agent-evals/<candidate>-vs-<baseline>-<timestamp>/`.

### 4. Review the report

Review every safety item, every regression item, plus the maximum five
sampled items (the bounded queue, ordered safety-first). The Markdown
report contains detailed traces only for the review queue; all other cases
are summarized by family/suite/risk.

### 5. Reject incomplete or blocked reports

An incomplete suite (provider failure after retry, or budget exhaustion)
or any safety/contract failure means the candidate is not approvable.
Fix the release, re-run, and re-review.

### 6. Approve a release

For approval:

1. Append/update the candidate release entry in
   `contracts/agent-evals/v3/graph-releases-v2.json` with
   `"approved_by": "tomi"` and the committed evidence path in
   `approval_evidence`.
2. Commit the evidence directory and the release activation change in a
   separate release-approval commit.
3. Never edit a prior release entry: the registry is append-only.

### 7. Grow the dataset from production failures

1. Add new production failures as `capability` cases in
   `conversation-trajectories-v3.json`.
2. Promote them to `regression` only after a corrected release passes the
   scripted path in CI.

## Remaining v1-only quality

Explanation/comparison quality and generative ranking-copy checks remain in
v1 until there is a structured product effect for them or a separately
approved text-grading design. The migration rationale lives in
`contracts/agent-evals/v3/migration-v3.md`.