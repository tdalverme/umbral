"""Contract gate for the checked-in web client generated from OpenAPI."""

import os
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_CONTRACT = REPOSITORY_ROOT / "contracts" / "openapi" / "v1" / "openapi.json"
WEB_WORKSPACE = REPOSITORY_ROOT / "apps" / "web"
GENERATED_CLIENT = WEB_WORKSPACE / "src" / "lib" / "api" / "generated"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _npm_command() -> str:
    return os.environ.get("NPM_EXECUTABLE", "npm.cmd" if os.name == "nt" else "npm")


def test_generated_web_client_is_regenerated_without_a_diff() -> None:
    """Catch a published OpenAPI change that leaves checked-in client output stale."""

    assert OPENAPI_CONTRACT.is_file(), (
        "published OpenAPI contract is missing: "
        f"{OPENAPI_CONTRACT}; export it before generating the web client"
    )
    assert GENERATED_CLIENT.is_dir(), (
        "generated web client directory is missing: "
        f"{GENERATED_CLIENT}; run `npm run api:generate --workspace @umbral/web`"
    )

    generation = _run(
        _npm_command(), "run", "api:generate", "--workspace", "@umbral/web"
    )
    assert generation.returncode == 0, (
        "OpenAPI client generation failed; run "
        "`npm run api:generate --workspace @umbral/web` locally.\n"
        f"stdout:\n{generation.stdout}\nstderr:\n{generation.stderr}"
    )

    status = _run("git", "status", "--short", "--", str(GENERATED_CLIENT))
    assert status.returncode == 0, status.stderr
    diff = _run("git", "diff", "--no-ext-diff", "HEAD", "--", str(GENERATED_CLIENT))
    assert diff.returncode == 0, diff.stderr
    assert not status.stdout.strip(), (
        "generated web client drifted from the published OpenAPI contract. "
        "Run `npm run api:generate --workspace @umbral/web` and commit the output.\n"
        f"git status:\n{status.stdout}\ngit diff:\n{diff.stdout}"
    )


def test_web_api_module_has_no_manual_dto_locations() -> None:
    """Catch hand-written DTO directories that can silently diverge from OpenAPI."""

    assert GENERATED_CLIENT.is_dir(), (
        "web API DTOs must be generated under "
        f"{GENERATED_CLIENT}; the generated directory is missing"
    )

    api_root = GENERATED_CLIENT.parent
    manual_dto_locations = [
        path
        for name in ("dto", "dtos", "models", "schemas", "types")
        for path in [api_root / name]
        if path.exists()
    ]
    manual_dto_files = [
        path
        for path in api_root.rglob("*.ts")
        if GENERATED_CLIENT not in path.parents
        and any(token in path.stem.lower() for token in ("dto", "model", "schema"))
    ]

    assert not manual_dto_locations and not manual_dto_files, (
        "manual web API DTOs are forbidden; keep generated types only under "
        f"{GENERATED_CLIENT}. Found: "
        + ", ".join(
            str(path.relative_to(REPOSITORY_ROOT))
            for path in [*manual_dto_locations, *manual_dto_files]
        )
    )
