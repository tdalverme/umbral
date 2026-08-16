"""Trajectory v2 invariants and strict release gate."""

from __future__ import annotations

import pytest

from umbral.application.agent_evals.trajectories.contracts import (
    MANDATORY_INVARIANTS,
    BindingSnapshot,
    DurableStateSnapshot,
    QuestionSnapshot,
    TrajectoryCase,
    TrajectoryDataset,
    TrajectoryGateBlocked,
    TrajectoryTrace,
    TrajectoryValidationError,
    TurnEffectRecord,
)
from umbral.application.agent_evals.trajectories.gate import evaluate_suite
from umbral.application.agent_evals.trajectories.invariants import (
    evaluate_invariant,
)
from umbral.application.agent_evals.trajectories.loader import (
    parse_trajectory_dataset,
)


def _case(
    *,
    case_id: str = "c1",
    family: str = "context_continuity",
    invariants: tuple[str, ...] = MANDATORY_INVARIANTS,
) -> TrajectoryCase:
    return TrajectoryCase(
        id=case_id,
        family=family,
        initial_state={},
        turns=(),
        final_state={"zones": [], "active_subjects": ["luminosidad"]},
        invariants=invariants,
    )


def _dataset(cases: tuple[TrajectoryCase, ...] = (_case(),)) -> TrajectoryDataset:
    return TrajectoryDataset(
        contract_version="2",
        registry_version="conversation-trajectories-v2",
        cases=cases,
    )


def _passing_trace(case_id: str) -> TrajectoryTrace:
    return TrajectoryTrace(
        case_id=case_id,
        durable_states=(
            DurableStateSnapshot(
                turn_index=0,
                state={"zones": [], "active_subjects": ["luminosidad"]},
            ),
        ),
        questions=(),
        turn_effects=(),
        bindings=(),
        verified_target_ids=(),
    )


def _effect(
    *,
    effect_key: str,
    status: str,
    confirmed: bool = True,
    object_id: str | None = None,
    target_ids: tuple[str, ...] = (),
) -> TurnEffectRecord:
    return TurnEffectRecord(
        turn_index=0,
        effect_key=effect_key,
        status=status,
        confirmed=confirmed,
        object_type="radar" if object_id else None,
        object_id=object_id,
        target_ids=target_ids,
    )


def test_all_mandatory_invariants_pass_on_a_clean_trace() -> None:
    trace = _passing_trace("c1")
    case = _case()

    verdicts = tuple(
        evaluate_invariant(invariant_id=invariant_id, case=case, trace=trace)
        for invariant_id in MANDATORY_INVARIANTS
    )

    assert all(verdict.passed for verdict in verdicts)


def test_final_state_mismatch_is_detected() -> None:
    case = _case()
    trace = TrajectoryTrace(
        case_id="c1",
        durable_states=(
            DurableStateSnapshot(turn_index=0, state={"zones": ["palermo"]}),
        ),
    )

    verdict = evaluate_invariant(
        invariant_id="final_state_matches_expected", case=case, trace=trace
    )

    assert verdict.passed is False
    assert "zones" in verdict.detail


def test_unconfirmed_material_effect_fails_safety_invariant() -> None:
    case = _case()
    trace = TrajectoryTrace(
        case_id="c1",
        turn_effects=(
            _effect(
                effect_key="filter.set",
                status="applied",
                confirmed=False,
                object_id="p1",
                target_ids=("p1",),
            ),
        ),
        verified_target_ids=("p1",),
    )

    verdict = evaluate_invariant(
        invariant_id="no_unconfirmed_material_effect", case=case, trace=trace
    )

    assert verdict.passed is False
    assert "unconfirmed_material" in verdict.detail


def test_wrong_target_mutation_is_detected() -> None:
    case = _case()
    trace = TrajectoryTrace(
        case_id="c1",
        turn_effects=(
            _effect(
                effect_key="preference.remembered",
                status="applied",
                object_id="other-radar",
                target_ids=("p1",),
            ),
        ),
        verified_target_ids=("p1",),
    )

    verdict = evaluate_invariant(
        invariant_id="no_wrong_target_mutation", case=case, trace=trace
    )

    assert verdict.passed is False
    assert "other-radar" in verdict.detail


def test_forbidden_binding_with_matcher_is_computable_failure() -> None:
    case = _case()
    trace = TrajectoryTrace(
        case_id="c1",
        bindings=(
            BindingSnapshot(
                turn_index=0,
                kind="forbidden",
                matcher_type="semantic_feature",
                embedding_version_id=None,
                confidence=0.0,
                mode="soft",
            ),
        ),
    )

    verdict = evaluate_invariant(
        invariant_id="forbidden_bindings_are_non_computable", case=case, trace=trace
    )

    assert verdict.passed is False


def test_repeated_answered_question_is_detected() -> None:
    case = _case()
    trace = TrajectoryTrace(
        case_id="c1",
        questions=(
            QuestionSnapshot(turn_index=0, slot="zona", answered=True, value="palermo"),
            QuestionSnapshot(turn_index=1, slot="zona", answered=True, value="palermo"),
        ),
    )

    verdict = evaluate_invariant(
        invariant_id="no_repeated_answered_question", case=case, trace=trace
    )

    assert verdict.passed is False
    assert "repeated_question" in verdict.detail


def test_suite_with_all_passing_cases_passes_the_gate() -> None:
    dataset = _dataset((_case(), _case(case_id="c2")))
    traces = {case.id: _passing_trace(case.id) for case in dataset.cases}

    suite = evaluate_suite(dataset=dataset, traces_by_case=traces)

    assert suite.blocked is False
    assert all(result.success for result in suite.case_results)


def test_suite_with_one_failure_blocks_on_critical_rate() -> None:
    dataset = _dataset((_case(), _case(case_id="c2")))
    traces = {
        "c1": _passing_trace("c1"),
        "c2": TrajectoryTrace(
            case_id="c2",
            turn_effects=(
                _effect(
                    effect_key="filter.set",
                    status="applied",
                    confirmed=False,
                    object_id="p2",
                    target_ids=("p2",),
                ),
            ),
            verified_target_ids=("p2",),
        ),
    }

    with pytest.raises(TrajectoryGateBlocked) as excinfo:
        evaluate_suite(dataset=dataset, traces_by_case=traces)
    assert any("critical_rate" in reason for reason in excinfo.value.reasons)


def test_wrong_target_mutations_block_the_gate() -> None:
    dataset = _dataset((_case(),))
    traces = {
        "c1": TrajectoryTrace(
            case_id="c1",
            durable_states=(
                DurableStateSnapshot(
                    turn_index=0,
                    state={"zones": [], "active_subjects": ["luminosidad"]},
                ),
            ),
            turn_effects=(
                _effect(
                    effect_key="preference.remembered",
                    status="applied",
                    object_id="wrong-radar",
                    target_ids=("p1",),
                ),
            ),
            verified_target_ids=("p1",),
        ),
    }

    with pytest.raises(TrajectoryGateBlocked) as excinfo:
        evaluate_suite(dataset=dataset, traces_by_case=traces)
    assert any("wrong_target" in reason for reason in excinfo.value.reasons)


def test_dataset_parser_requires_mandatory_invariants() -> None:
    payload = {
        "contract_version": "2",
        "registry_version": "conversation-trajectories-v2",
        "cases": [
            {
                "id": "c1",
                "family": "context_continuity",
                "initial_state": {},
                "turns": [
                    {
                        "user": "quiero un depto luminoso",
                        "expected_acts": ["create_radar", "express_preference"],
                        "expected_effects": ["radar.created"],
                        "forbidden": [],
                    }
                ],
                "final_state": {"zones": []},
                "invariants": ["final_state_matches_expected"],
            }
        ],
    }

    with pytest.raises(TrajectoryValidationError) as excinfo:
        parse_trajectory_dataset(payload)
    assert any("missing_mandatory" in code for code in excinfo.value.error_codes)


def test_dataset_parser_rejects_unknown_invariant() -> None:
    payload = {
        "contract_version": "2",
        "registry_version": "conversation-trajectories-v2",
        "cases": [
            {
                "id": "c1",
                "family": "context_continuity",
                "initial_state": {},
                "turns": [
                    {
                        "user": "hola",
                        "expected_acts": ["query"],
                        "expected_effects": ["query"],
                        "forbidden": [],
                    }
                ],
                "final_state": {},
                "invariants": [*MANDATORY_INVARIANTS, "made_up"],
            }
        ],
    }

    with pytest.raises(TrajectoryValidationError) as excinfo:
        parse_trajectory_dataset(payload)
    assert "trajectory_evals.unknown_invariant:made_up" in excinfo.value.error_codes


def test_parser_accepts_a_complete_trajectory_dataset() -> None:
    payload = {
        "contract_version": "2",
        "registry_version": "conversation-trajectories-v2",
        "cases": [
            {
                "id": "reported-zone-loop",
                "family": "context_continuity",
                "initial_state": {"profiles": [], "session": {"profile_id": None}},
                "turns": [
                    {
                        "user": "Quiero un depto luminoso",
                        "expected_acts": ["create_radar", "express_preference"],
                        "expected_effects": [
                            "radar.created",
                            "preference.remembered",
                        ],
                        "forbidden": ["ask_zone_before_persist"],
                    }
                ],
                "final_state": {"zones": [], "active_subjects": ["luminosidad"]},
                "invariants": [
                    *MANDATORY_INVARIANTS,
                    "no_repeated_answered_question",
                ],
            }
        ],
    }

    dataset = parse_trajectory_dataset(payload)

    assert dataset.cases[0].id == "reported-zone-loop"
    assert set(dataset.cases[0].invariants) >= set(MANDATORY_INVARIANTS)