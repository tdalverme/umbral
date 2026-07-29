"""Contract checks for the versioned public OpenAPI surface."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPOSITORY_ROOT / "contracts" / "openapi" / "v1" / "openapi.json"
EXPORT_SCRIPT = REPOSITORY_ROOT / "scripts" / "export-openapi.ps1"
CONTRACT_CHECK = REPOSITORY_ROOT / "scripts" / "check-contracts.ps1"
EXPECTED_OPERATION_IDS = {
    "/health": "getRuntimeHealth",
    "/ready": "getRuntimeReadiness",
    "/version": "getRuntimeVersion",
}
EXPECTED_GET_OPERATION_IDS = {
    f"GET {path}": operation_id for path, operation_id in EXPECTED_OPERATION_IDS.items()
}


def _read_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    assert path.is_file(), f"versioned OpenAPI contract is missing: {path}"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), "OpenAPI contract must be a mapping"
    return cast(dict[str, Any], document)


def _operation_ids(document: dict[str, Any]) -> dict[str, str]:
    paths = document.get("paths")
    assert isinstance(paths, dict), "OpenAPI document must declare paths"
    operation_ids: dict[str, str] = {}
    for path, path_item in paths.items():
        assert isinstance(path, str)
        assert isinstance(path_item, dict)
        for method, operation in path_item.items():
            if method.lower() not in {"get", "put", "post", "delete", "patch", "head"}:
                continue
            assert isinstance(operation, dict)
            operation_id = operation.get("operationId")
            assert isinstance(operation_id, str) and operation_id
            operation_ids[f"{method.upper()} {path}"] = operation_id
    return operation_ids


def _run_powershell(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    assert script.is_file(), f"required contract gate is missing: {script}"
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(script),
            *arguments,
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _export_openapi(output_path: Path) -> subprocess.CompletedProcess[str]:
    return _run_powershell(EXPORT_SCRIPT, "-OutputPath", str(output_path))


def _check_compatibility(
    baseline_path: Path, candidate_path: Path
) -> subprocess.CompletedProcess[str]:
    return _run_powershell(
        CONTRACT_CHECK,
        "-BaselinePath",
        str(baseline_path),
        "-CandidatePath",
        str(candidate_path),
    )


def test_openapi_export_is_deterministic_openapi_31_with_stable_operation_ids(
    tmp_path: Path,
) -> None:
    contract = _read_contract()
    assert contract["openapi"] == "3.1.0"
    assert _operation_ids(contract) == EXPECTED_GET_OPERATION_IDS

    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first_result = _export_openapi(first)
    second_result = _export_openapi(second)

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    assert first.read_bytes() == second.read_bytes()
    exported = json.loads(first.read_text(encoding="utf-8"))
    assert exported["openapi"] == "3.1.0"
    assert _operation_ids(exported) == EXPECTED_GET_OPERATION_IDS


def test_optional_schema_addition_is_compatible_with_contract_major_one(
    tmp_path: Path,
) -> None:
    baseline = _read_contract()
    candidate = copy.deepcopy(baseline)
    candidate["components"]["schemas"]["Health"]["properties"]["release_id"] = {
        "type": "string"
    }

    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    candidate_path.write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    result = _check_compatibility(baseline_path, candidate_path)

    assert result.returncode == 0, result.stderr


def test_breaking_same_major_contract_change_is_rejected(tmp_path: Path) -> None:
    baseline = _read_contract()
    candidate = copy.deepcopy(baseline)
    candidate["components"]["schemas"]["Health"]["properties"]["status"] = {
        "type": "integer"
    }

    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    candidate_path.write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    result = _check_compatibility(baseline_path, candidate_path)

    assert result.returncode != 0
    assert "breaking" in (result.stdout + result.stderr).lower()
