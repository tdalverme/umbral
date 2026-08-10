"""Structure conformance of the model provider ADR deliverable (T046)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "decision-records" / "0001-model-provider.md"

_CRITERIA = (
    "costo",
    "calidad",
    "latencia",
    "privacidad",
    "operabilidad",
)


def test_adr_exists_and_is_versioned() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    assert "Status" in text and "Aceptado" in text
    assert "Version" in text
    assert "Date" in text


def test_adr_compares_alternatives_with_the_five_criteria() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    for criterion in _CRITERIA:
        assert criterion in text.lower(), criterion


def test_adr_records_decision_risks_and_monitoring() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    assert "## Decision" in text
    assert "## Consequences" in text
    assert "## Monitoring" in text
    assert "## Alternatives considered" in text


def test_adr_is_referenced_by_the_plan_and_harness_surface() -> None:
    plan = ROOT / "specs" / "012-graph-evals-ops" / "plan.md"
    assert "0001-model-provider.md" in plan.read_text(encoding="utf-8")
