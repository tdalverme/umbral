"""US4: zero-match diagnostics surfaces concept-level hard criteria (FR-014)."""

from __future__ import annotations

from typing import cast

from tests.support.radar import build_listing, build_profile

from umbral.application.radar.diagnostics import build_diagnostics

SUPPORTED = ("palermo", "recoleta", "belgrano")


def test_diagnostics_report_concept_level_hard_criteria() -> None:
    profile = build_profile(zones=("palermo",), budget_max=2000.0)
    candidates = (build_listing(total_cost=1500.0),)

    diagnostics = build_diagnostics(
        profile=profile,
        candidates=candidates,
        supported_neighborhoods=SUPPORTED,
        hard_criteria=("mascotas", "acceso_escuela"),
    )

    active = cast(list[str], diagnostics["active_criteria"])
    counts = cast(dict[str, int], diagnostics["exclusion_counts"])
    proposals = cast(list[dict[str, object]], diagnostics["relaxation_proposals"])
    assert "criterion:mascotas" in active
    assert "criterion:acceso_escuela" in active
    assert "criterion:mascotas" in counts
    assert any(
        proposal["criterion"] == "mascotas"
        and proposal["kind"] == "relax_criterion"
        for proposal in proposals
    )


def test_diagnostics_without_hard_criteria_are_unchanged() -> None:
    profile = build_profile(zones=("palermo",))
    diagnostics = build_diagnostics(
        profile=profile,
        candidates=(build_listing(),),
        supported_neighborhoods=SUPPORTED,
    )

    active = cast(list[str], diagnostics["active_criteria"])
    proposals = cast(list[dict[str, object]], diagnostics["relaxation_proposals"])
    assert "criterion:mascotas" not in active
    assert "relax_criterion" not in {
        proposal["kind"] for proposal in proposals
    }


def test_diagnostics_do_not_duplicate_profile_hard_filters() -> None:
    profile = build_profile(zones=("palermo",), budget_max=2000.0)
    diagnostics = build_diagnostics(
        profile=profile,
        candidates=(build_listing(total_cost=1500.0),),
        supported_neighborhoods=SUPPORTED,
        hard_criteria=("budget_max", "mascotas"),
    )

    active = cast(list[str], diagnostics["active_criteria"])
    assert "criterion:budget_max" not in active
    assert "criterion:mascotas" in active
