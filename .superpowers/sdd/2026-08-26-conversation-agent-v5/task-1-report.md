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
