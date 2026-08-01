# Task 11 report — Railway service contracts

## Implementation commit

`df58964` (`build: define Railway beta services`)

## RED / GREEN

- **RED:** the specified pytest command initially stopped at collection because
  this worktree's `.venv` does not install `umbral` (`ModuleNotFoundError`).
  Re-running with `PYTHONPATH=src` exposed the intended failures: missing
  Railway service contract, variable inventory and validator, plus the
  worker-only runtime `ENTRYPOINT` (9 failed, 5 passed).
- **GREEN:** after adding the internal contract and multi-process runtime,
  `PYTHONPATH=src .venv\Scripts\python.exe -m pytest
  tests/contract/test_railway_configuration.py tests/contract/test_release_manifest.py -q`
  passed with 14 tests.
- **Additional RED/GREEN:** the first runtime Docker build showed that
  `COPY alembic.ini alembic ./` flattened the Alembic directory and left
  `/app/alembic` unavailable to the runtime stage. A focused regression test
  failed, then passed after separating the copies; the final contract suite has
  15 passing tests.

## Commands and results

| Command | Result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest tests/contract/test_railway_configuration.py tests/contract/test_release_manifest.py -q` | Failed at collection: worktree environment lacks installed `umbral`. |
| `PYTHONPATH=src .venv\Scripts\python.exe -m pytest tests/contract/test_railway_configuration.py tests/contract/test_release_manifest.py -q` | Passed: 15 tests. Pytest emitted a non-fatal warning that it cannot write `.pytest_cache` in this worktree. |
| `.venv\Scripts\ruff.exe check tests/contract/test_railway_configuration.py tests/contract/test_release_manifest.py` | Passed. |
| `git diff --check` | Passed. |
| `.\scripts\deploy\validate-railway-config.ps1 -ManifestPath tests\fixtures\release-manifests\valid.json` | Passed; resolved immutable web and runtime digests. |
| `docker build --file Dockerfile.runtime --tag umbral-runtime:plan-check .` | Passed after the Alembic-copy fix. The initial attempt timed out at 60 seconds after reaching the actual missing-directory error. |
| `docker build --file apps/web/Dockerfile --tag umbral-web:plan-check .` | Timed out at 64 seconds with no additional build output; not retried, per bounded-time verification policy. |

## Files

- `Dockerfile.runtime`: safe default command and Alembic assets copied to the
  runtime image.
- `apps/web/Dockerfile`: explicit Railway-compatible bind host and port.
- `infra/railway/services.json`: internal release-artifact contract for web,
  API, worker and scheduler.
- `infra/railway/variables.example.json`: scoped variable-name inventory only;
  no secret values.
- `scripts/deploy/validate-railway-config.ps1`: manifest-aware static contract
  validator.
- `tests/contract/test_railway_configuration.py` and
  `tests/contract/test_release_manifest.py`: service, artifact and runtime
  contract coverage.
- `docs/architecture/decisions/0002-runtime-platform.md`: Railway/Neon/R2
  preview exception while preserving the deferred production decision.

## Decisions and risks

- `services.json` is explicitly an **internal** contract. Its
  `release_artifact` references (`web` and `runtime`) are resolved by the
  repository validator against a release manifest; it is not presented as a
  Railway-native configuration file.
- The three runtime services share the immutable `runtime` artifact. Railway
  private networking is automatic, while `public_domain: true` is limited to
  the web service.
- Railway policy values use the current enums `ON_FAILURE`, `ALWAYS` and
  `NEVER`; scheduler is `*/5 * * * *` in UTC; serverless sleep is enabled only
  for web/API.
- The runtime Docker build is verified. The web Docker build remains
  unverified because Docker timed out; static Dockerfile and contract checks
  pass. The worktree's Python installation and pytest-cache permissions are
  environment limitations, not changed by this task.
