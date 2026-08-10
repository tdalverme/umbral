# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""explain_match tool tests (FR-015/FR-016, T033)."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from tests.support.tools import build_executor, call_tool, payload


def test_explain_match_returns_persisted_evidence() -> None:
    executor, _ = build_executor()
    result = call_tool(executor, "explain_match", {"listing_id": str(UUID(int=70))})
    assert payload(result)["score_version"] == "scoring-policy-v1"
    reasons = cast(Any, payload(result)["reasons"])
    assert reasons[0]["criterion_key"] == "presupuesto"
    assert reasons[0]["evidence_level"] == "strong"
    assert payload(result)["risks"] == ["Sin datos de ruido"]
    assert payload(result)["missing_data"] == ["ruido"]
    refs = cast(Any, payload(result)["evidence_refs"])
    assert refs[0]["kind"] == "observation"


def test_explain_match_denied_when_no_run() -> None:
    from tests.support.tools import FakeRadar, FakeServices

    class NoRunRadar(FakeRadar):
        def latest_run_of(self, profile):
            return None

    executor, _ = build_executor(services=FakeServices(radar=NoRunRadar()))
    result = call_tool(executor, "explain_match", {"listing_id": str(UUID(int=70))})
    assert result.status == "error"
    assert result.error_code == "tool.no_run"
