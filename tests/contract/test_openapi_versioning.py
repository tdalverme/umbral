"""Contract checks for the versioned public OpenAPI surface."""
# ruff: noqa: E501

from __future__ import annotations

import copy
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPOSITORY_ROOT / "contracts" / "openapi" / "v1" / "openapi.json"
EXPORT_SCRIPT = REPOSITORY_ROOT / "scripts" / "export-openapi.ps1"
CONTRACT_CHECK = REPOSITORY_ROOT / "scripts" / "check-contracts.ps1"
EXPECTED_OPERATION_IDS = {
    "GET /health": "getRuntimeHealth",
    "GET /ready": "getRuntimeReadiness",
    "GET /version": "getRuntimeVersion",
    "POST /api/v1/auth/magic-link-requests": "requestMagicLink",
    "POST /api/v1/auth/magic-link-confirmations": "confirmMagicLink",
    "GET /api/v1/auth/session": "getCurrentSession",
    "POST /api/v1/auth/logout": "logoutCurrentSession",
    "POST /api/v1/integrations/email/resend-events": "receiveResendEvent",
    "GET /api/v1/imports/quarantine/{record_id}": "getQuarantineRecord",
    "GET /api/v1/imports/runs/{run_id}": "getImportRun",
    "GET /api/v1/imports/runs/{run_id}/quality": "getImportQuality",
    "GET /api/v1/imports/runs/{run_id}/quality/download": "downloadImportQuality",
    "POST /api/v1/imports/batches": "submitImportBatch",
    "GET /api/v1/listings/{listing_id}": "getListingDetail",
    "GET /api/v1/search-profiles": "listSearchProfiles",
    "GET /api/v1/search-profiles/{search_profile_id}": "getSearchProfile",
    "PATCH /api/v1/search-profiles/{search_profile_id}": "updateSearchProfile",
    "POST /api/v1/search-profiles": "createSearchProfile",
    "POST /api/v1/search-profiles/{search_profile_id}/status": "setSearchProfileStatus",
    "GET /api/v1/search-profiles/{search_profile_id}/matches": "listMatches",
    "GET /api/v1/search-profiles/{search_profile_id}/explanations": "listExplanations",
    "GET /api/v1/search-profiles/{search_profile_id}/explanations/{listing_id}": "getExplanation",
    "POST /api/v1/search-profiles/{search_profile_id}/comparisons": "createComparison",
    "GET /api/v1/search-profiles/{search_profile_id}/comparison-shortlist": "getComparisonShortlist",
    "PUT /api/v1/search-profiles/{search_profile_id}/comparison-shortlist": "setComparisonShortlist",
    "GET /api/v1/search-profiles/{search_profile_id}/decision-items": "listDecisionItems",
    "POST /api/v1/search-profiles/{search_profile_id}/feedback": "recordFeedback",
    "GET /api/v1/search-profiles/{search_profile_id}/learning-proposals": "listLearningProposals",
    "PUT /api/v1/search-profiles/{search_profile_id}/learning-proposals/{proposal_id}": "expandLearningProposal",
    "POST /api/v1/search-profiles/{search_profile_id}/learning-proposals/{proposal_id}/confirm": "confirmLearningProposal",
    "POST /api/v1/search-profiles/{search_profile_id}/learning-proposals/{proposal_id}/reject": "rejectLearningProposal",
    "POST /api/v1/search-profiles/{search_profile_id}/learning-proposals/{proposal_id}/undo": "undoLearningProposal",
    "GET /api/v1/search-profiles/{search_profile_id}/update-proposals": "listUpdateProposals",
    "GET /api/v1/search-profiles/{search_profile_id}/preferences": "listSearchProfilePreferences",
    "GET /api/v1/chat/sessions": "listChatSessions",
    "GET /api/v1/chat/sessions/{session_id}": "getChatSession",
    "GET /api/v1/chat/sessions/{session_id}/messages": "listChatSessionMessages",
    "POST /api/v1/chat/sessions": "createSession",
    "POST /api/v1/chat/sessions/{session_id}/messages": "sendChatMessage",
    "POST /api/v1/chat/sessions/{session_id}/resume": "resumeChatSession",
    "POST /api/v1/chat/sessions/{session_id}/runs/{run_id}/decision": "decideChatRun",
    "POST /api/v1/product-events": "emitProductEvent",
    "GET /api/v1/agent/ops/overview": "agentOpsOverview",
    "GET /api/v1/notifications/inbox": "get_inbox_api_v1_notifications_inbox_get",
    "PATCH /api/v1/notifications/inbox/{decision_id}": "patch_inbox_api_v1_notifications_inbox__decision_id__patch",
    "GET /api/v1/notifications/preferences": "get_preferences_api_v1_notifications_preferences_get",
    "PUT /api/v1/notifications/preferences": "put_preferences_api_v1_notifications_preferences_put",
    "POST /api/v1/notifications/unsubscribe": "unsubscribe_api_v1_notifications_unsubscribe_post",
    "GET /api/v1/urban/signals": "getUrbanSignals",
}
EXPECTED_GET_OPERATION_IDS = EXPECTED_OPERATION_IDS


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


def _write_contract_pair(
    tmp_path: Path, baseline: dict[str, Any], candidate: dict[str, Any]
) -> tuple[Path, Path]:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    candidate_path.write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return baseline_path, candidate_path


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

    baseline_path, candidate_path = _write_contract_pair(tmp_path, baseline, candidate)

    result = _check_compatibility(baseline_path, candidate_path)

    assert result.returncode == 0, result.stderr


def test_breaking_same_major_contract_change_is_rejected(tmp_path: Path) -> None:
    baseline = _read_contract()
    candidate = copy.deepcopy(baseline)
    candidate["components"]["schemas"]["Health"]["properties"]["status"] = {
        "type": "integer"
    }

    baseline_path, candidate_path = _write_contract_pair(tmp_path, baseline, candidate)

    result = _check_compatibility(baseline_path, candidate_path)

    assert result.returncode != 0
    assert "breaking" in (result.stdout + result.stderr).lower()


def _remove_health_path(candidate: dict[str, Any]) -> None:
    candidate["paths"].pop("/health")


def _remove_health_get(candidate: dict[str, Any]) -> None:
    candidate["paths"]["/health"].pop("get")


def _change_health_operation_id(candidate: dict[str, Any]) -> None:
    candidate["paths"]["/health"]["get"]["operationId"] = "differentOperation"


def _remove_health_required_status(candidate: dict[str, Any]) -> None:
    candidate["components"]["schemas"]["Health"]["required"] = []


def _remove_readiness_response(candidate: dict[str, Any]) -> None:
    candidate["paths"]["/ready"]["get"]["responses"].pop("503")


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(_remove_health_path, id="path"),
        pytest.param(_remove_health_get, id="method"),
        pytest.param(_change_health_operation_id, id="operation-id"),
        pytest.param(_remove_health_required_status, id="required-property"),
        pytest.param(_remove_readiness_response, id="response-status"),
    ],
)
def test_breaking_path_and_schema_changes_are_rejected(
    tmp_path: Path, mutation: Callable[[dict[str, Any]], None]
) -> None:
    baseline = _read_contract()
    candidate = copy.deepcopy(baseline)
    mutation(candidate)
    baseline_path, candidate_path = _write_contract_pair(tmp_path, baseline, candidate)

    result = _check_compatibility(baseline_path, candidate_path)

    assert result.returncode != 0
    assert "breaking" in (result.stdout + result.stderr).lower()


def test_removing_required_security_is_rejected(tmp_path: Path) -> None:
    baseline = _read_contract()
    baseline["components"]["securitySchemes"] = {
        "runtimeBearer": {"scheme": "bearer", "type": "http"}
    }
    baseline["paths"]["/health"]["get"]["security"] = [{"runtimeBearer": []}]
    candidate = copy.deepcopy(baseline)
    candidate["paths"]["/health"]["get"].pop("security")
    baseline_path, candidate_path = _write_contract_pair(tmp_path, baseline, candidate)

    result = _check_compatibility(baseline_path, candidate_path)

    assert result.returncode != 0
    assert "breaking" in (result.stdout + result.stderr).lower()
