# T008 report: architecture dependency fixtures

## Status

DONE. The fixture corpus and test-only source scanner are committed together;
no production modules, Import Linter configuration, or harness scripts were
changed.

## RED evidence

The tests were written before the scanner implementation and ran with the
expected missing-helper failure:

```text
& .venv\Scripts\python.exe -m pytest tests/architecture/test_dependency_rules.py -q
FFF.                                                                     [100%]
3 failed, 1 passed in 0.17s
NameError: name 'scan_fixture_graph' is not defined
```

The passing test only checked that the fixture source did not contain a
production import; the three graph assertions correctly failed because the
test-only scanner did not yet exist.

## GREEN evidence

The minimum AST-based scanner now resolves only local fixture imports, reports
forbidden direct edges, and adds deterministic allowed prefixes to expose a
full transitive violation path. The graph is source-scanned and never imports
`src.umbral` or contacts an external service.

```text
& .venv\Scripts\python.exe -m pytest -q
....                                                                     [100%]
4 passed in 0.06s

& .venv\Scripts\python.exe -m ruff check tests/architecture
All checks passed!

fixture imports OK
```

The positive graph contains all six layers and permitted edges such as
`application -> domain`. The direct negative graph names
`domain -> infrastructure`. The transitive graph names
`agent -> application -> infrastructure` while preserving the permitted
`agent -> application` prefix.

`git diff --check` exited `0`. Existing `.specify/` and
`specs/001-foundation-runtime/tasks.md` changes were preserved and are not
part of this task's commit.
