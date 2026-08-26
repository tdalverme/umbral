# Task 1 Report — V5.0 Stage-attributed Evaluation Evidence

## Implementation summary

Added the isolated `agent_evals.v4` evidence contracts, deterministic grader,
and safe reporting projections. The implementation retains the first explicit
turn failure stage, classifies it as safety, product, provider, harness, or
success, and adds the `evals_v4.invalid_act_reached_policy` safety check.

Reporting counts candidate failures by stage, emits one bounded representative
sample per `(family, failure_stage, reason_code)`, recursively redacts the
required secret keys case-insensitively, and omits untrusted listing values.
The existing V4 conversation implementation was not modified.

## RED evidence

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/unit/application/agent_evals/v4 -q
```

Result: expected RED, `2 errors during collection` (exit 2). Both new test
modules failed with `ModuleNotFoundError: No module named
'umbral.application.agent_evals.v4.contracts'`, because the V4 contracts and
grader did not yet exist.

## GREEN and regression evidence

Focused V4 command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/unit/application/agent_evals/v4 -q
```

Result: `7 passed in 0.06s`.

Requested V3 grading/reporting regression command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/unit/application/agent_evals/v3/test_grading.py tests/unit/application/agent_evals/v3/test_reporting.py -q --basetemp .umbral-local\pytest-task-1
```

Result: `18 passed in 0.12s`.

Additional static checks:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m mypy src/umbral/application/agent_evals/v4 tests/unit/application/agent_evals/v4
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m ruff check src/umbral/application/agent_evals/v4 tests/unit/application/agent_evals/v4
```

Results: `Success: no issues found in 6 source files`; `All checks passed!`.

## Files changed

- `src/umbral/application/agent_evals/v4/__init__.py`
- `src/umbral/application/agent_evals/v4/contracts.py`
- `src/umbral/application/agent_evals/v4/grading.py`
- `src/umbral/application/agent_evals/v4/reporting.py`
- `tests/unit/application/agent_evals/v4/test_grading.py`
- `tests/unit/application/agent_evals/v4/test_reporting.py`
- `.superpowers/sdd/2026-08-26-conversation-agent-v5/task-1-report.md`

## Self-review

- Verified the required public evidence fields match the brief verbatim.
- Verified stage selection uses the first explicit turn stage.
- Verified provider and contract stages take precedence over safety/product
  classification; the invalid-schema/policy-input safety check is independent
  and fails only for that exact condition.
- Verified JSON and Markdown are deterministic, represent only bounded
  structured stage evidence, redact required keys recursively, and omit
  untrusted listing values.
- Verified sampling is deduplicated by family, stage, and reason code.
- Ran `git diff --check`; no whitespace errors were reported for Task 1 files.

## Concerns

The first V3 regression invocation encountered a Windows permission denial
creating pytest's default temp directory (`C:\Users\Usuario\AppData\Local\Temp\pytest-of-Usuario`). Re-running the same requested V3 suites with a
worktree-local `--basetemp` passed all 18 tests. This is an environment issue,
not a Task 1 code failure.

## Fix Round 1 — bounded safe stage evidence

### RED evidence

Added four negative tests before the corresponding production changes:

- `test_neutral_and_nested_fields_cannot_emit_untrusted_listing_bodies`
- `test_diagnostic_field_values_cannot_emit_untrusted_listing_bodies`
- `test_dynamic_field_names_cannot_emit_untrusted_listing_bodies`
- `test_every_emitted_string_has_a_deterministic_hard_maximum`

Command:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/unit/application/agent_evals/v4/test_reporting.py -q
```

Result: expected RED, `2 failed, 3 passed in 0.36s`. The first test found the
full untrusted listing body under neutral `selected.description`, `payload`,
and `description` paths. The second found a 257-character reason code emitted
without a hard bound.

The later diagnostic-value and dynamic-field-name tests each also produced the
expected RED (`1 failed`) before their production changes: a short listing body
was emitted under `status`, then as a mapping key.

### Fix and GREEN evidence

Replaced key-name listing heuristics with a strict field projection: only
allowlisted diagnostic field names are retained, and only numeric, boolean, or
null values are emitted for them. Unknown, nested, and string field values are
summarized through an omitted-field count. Every remaining dynamic report
string is deterministically capped at 256 characters. Short reason codes remain
intact.

Final verification:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/unit/application/agent_evals/v4 -q
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m pytest tests/unit/application/agent_evals/v3/test_grading.py tests/unit/application/agent_evals/v3/test_reporting.py -q --basetemp .umbral-local\pytest-task-1
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m mypy src/umbral/application/agent_evals/v4 tests/unit/application/agent_evals/v4
D:\Tomi\dev\umbral\.venv\Scripts\python.exe -m ruff check src/umbral/application/agent_evals/v4 tests/unit/application/agent_evals/v4
```

Results: `11 passed in 0.06s`; `18 passed in 0.12s`; `Success: no issues found
in 6 source files`; `All checks passed!`.

### Self-review

- Confirmed arbitrary content in neutral, nested, diagnostic-value, and
  dynamic-key evidence fields is omitted before it can reach JSON or Markdown.
- Confirmed map keys are projected only from fixed allowlists, while every
  remaining dynamic report string is capped.
- Confirmed existing secret redaction, deterministic ordering, bounded sample
  selection, and V3 regression behavior remain covered by the final suite.
