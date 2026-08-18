"""Deterministic invariant evaluators for conversational trajectories v2.

Each evaluator maps a trace (evidence collected by the runner) to a pass/fail
verdict with a short, auditable reason. No evaluator performs I/O; the runner
collects the evidence and the gate aggregates verdicts.
"""

from __future__ import annotations

from collections.abc import Mapping

from umbral.application.agent_evals.trajectories.contracts import (
    BindingSnapshot,
    InvariantVerdict,
    QuestionSnapshot,
    TrajectoryCase,
    TrajectoryTrace,
    TurnEffectRecord,
)

_MATERIAL_STATUSES = frozenset({"applied", "pending"})
# Durable changes to hard filters are the only material effects; soft
# preferences, radar creation and queries never require confirmation
# (FR-012/FR-013).
_MATERIAL_EFFECT_KEYS = frozenset({"filter.set", "filter.cleared"})


def evaluate_invariant(
    *,
    invariant_id: str,
    case: TrajectoryCase,
    trace: TrajectoryTrace,
) -> InvariantVerdict:
    """Dispatch one invariant to its deterministic evaluator."""
    evaluators = {
        "final_state_matches_expected": _final_state_matches_expected,
        "no_repeated_answered_question": _no_repeated_answered_question,
        "no_unconfirmed_material_effect": _no_unconfirmed_material_effect,
        "forbidden_bindings_are_non_computable": _forbidden_bindings_are_non_computable,
        "no_wrong_target_mutation": _no_wrong_target_mutation,
    }
    evaluator = evaluators.get(invariant_id)
    if evaluator is None:
        return InvariantVerdict(
            invariant_id=invariant_id,
            case_id=case.id,
            passed=False,
            detail="unknown_invariant",
        )
    return evaluator(case=case, trace=trace)


def _final_state_matches_expected(
    *,
    case: TrajectoryCase,
    trace: TrajectoryTrace,
) -> InvariantVerdict:
    if not trace.durable_states:
        return InvariantVerdict(
            invariant_id="final_state_matches_expected",
            case_id=case.id,
            passed=False,
            detail="no_durable_state_snapshots",
        )
    last = trace.durable_states[-1].state
    # Only the declared final_state fields are compared; extra snapshot
    # fields (ids, derived values) do not invalidate the expected state.
    mismatches = {
        key
        for key, expected_value in case.final_state.items()
        if last.get(key) != expected_value
    }
    if mismatches:
        return InvariantVerdict(
            invariant_id="final_state_matches_expected",
            case_id=case.id,
            passed=False,
            detail="mismatch:" + ",".join(sorted(mismatches)),
        )
    return InvariantVerdict(
        invariant_id="final_state_matches_expected",
        case_id=case.id,
        passed=True,
        detail="last_snapshot_matches_expected",
    )


def _no_repeated_answered_question(
    *,
    case: TrajectoryCase,
    trace: TrajectoryTrace,
) -> InvariantVerdict:
    """No question targets an answered slot whose recorded value stays active."""
    answered: dict[str, object] = {}
    for question in trace.questions:
        if not question.answered:
            continue
        previous = answered.get(question.slot, _MISSING)
        if previous is not _MISSING:
            return InvariantVerdict(
                invariant_id="no_repeated_answered_question",
                case_id=case.id,
                passed=False,
                detail=f"repeated_question:{question.slot}",
            )
        answered[question.slot] = question.value
    return InvariantVerdict(
        invariant_id="no_repeated_answered_question",
        case_id=case.id,
        passed=True,
        detail="no_repeated_answered_slot",
    )


def _no_unconfirmed_material_effect(
    *,
    case: TrajectoryCase,
    trace: TrajectoryTrace,
) -> InvariantVerdict:
    """No material effect is applied without a matching resolved confirmation.

    Material effects are hard-filter changes (set/clear). A filter.set on an
    open radar is additive and never requires confirmation; a pending change
    (or a cleared active filter) is material and must be confirmed (FR-012/13).
    """
    for effect in trace.turn_effects:
        if effect.effect_key not in _MATERIAL_EFFECT_KEYS:
            continue
        if effect.status == "pending":
            if not effect.confirmed:
                return InvariantVerdict(
                    invariant_id="no_unconfirmed_material_effect",
                    case_id=case.id,
                    passed=False,
                    detail=f"unconfirmed_material:{effect.effect_key}",
                )
            continue
        if effect.status == "applied" and not effect.confirmed:
            # Applied hard-filter change without confirmation: only additive
            # filter.set on an open radar is allowed (reason_code None);
            # clearing an active filter is always material.
            if effect.effect_key == "filter.cleared":
                return InvariantVerdict(
                    invariant_id="no_unconfirmed_material_effect",
                    case_id=case.id,
                    passed=False,
                    detail=f"unconfirmed_material:{effect.effect_key}",
                )
            if effect.reason_code is not None:
                return InvariantVerdict(
                    invariant_id="no_unconfirmed_material_effect",
                    case_id=case.id,
                    passed=False,
                    detail=f"unconfirmed_material:{effect.effect_key}",
                )
    return InvariantVerdict(
        invariant_id="no_unconfirmed_material_effect",
        case_id=case.id,
        passed=True,
        detail="all_material_effects_confirmed",
    )


def _forbidden_bindings_are_non_computable(
    *,
    case: TrajectoryCase,
    trace: TrajectoryTrace,
) -> InvariantVerdict:
    """Every forbidden binding has null matcher/embedding and zero confidence."""
    for binding in trace.bindings:
        if binding.kind != "forbidden":
            continue
        if (
            binding.matcher_type is not None
            or binding.embedding_version_id is not None
            or binding.confidence != 0.0
        ):
            return InvariantVerdict(
                invariant_id="forbidden_bindings_are_non_computable",
                case_id=case.id,
                passed=False,
                detail=f"computable_forbidden_binding:{binding.kind}",
            )
    return InvariantVerdict(
        invariant_id="forbidden_bindings_are_non_computable",
        case_id=case.id,
        passed=True,
        detail="forbidden_bindings_non_computable",
    )


def _no_wrong_target_mutation(
    *,
    case: TrajectoryCase,
    trace: TrajectoryTrace,
) -> InvariantVerdict:
    """Every mutated object id belongs to the verified target ids of the turn."""
    verified = set(trace.verified_target_ids)
    for effect in trace.turn_effects:
        if effect.status != "applied":
            continue
        if effect.object_id is not None and effect.object_id not in verified:
            return InvariantVerdict(
                invariant_id="no_wrong_target_mutation",
                case_id=case.id,
                passed=False,
                detail=f"wrong_target:{effect.object_id}",
            )
    return InvariantVerdict(
        invariant_id="no_wrong_target_mutation",
        case_id=case.id,
        passed=True,
        detail="all_mutations_on_verified_targets",
    )


_MISSING = object()


# Re-exported for introspection by the runner.
def required_evidence_for(invariant_id: str) -> tuple[str, ...]:
    return {
        "final_state_matches_expected": (
            "durable_states",
            "final_state",
        ),
        "no_repeated_answered_question": ("durable_states", "questions"),
        "no_unconfirmed_material_effect": ("turn_effects", "durable_states"),
        "forbidden_bindings_are_non_computable": ("bindings",),
        "no_wrong_target_mutation": ("turn_effects", "verified_target_ids"),
    }.get(invariant_id, ())


def turn_effects_are_material(effect: TurnEffectRecord) -> bool:
    return effect.status in _MATERIAL_STATUSES


def question_answered(
    question: QuestionSnapshot, answered: Mapping[str, object]
) -> bool:
    return question.answered and question.slot in answered


def latest_state(trace: TrajectoryTrace) -> Mapping[str, object]:
    if not trace.durable_states:
        return {}
    return trace.durable_states[-1].state


def binding_is_computable(binding: BindingSnapshot) -> bool:
    return (
        binding.matcher_type is not None or binding.embedding_version_id is not None
    )


def unconfirmed_material_effects(
    trace: TrajectoryTrace,
) -> tuple[TurnEffectRecord, ...]:
    return tuple(
        effect
        for effect in trace.turn_effects
        if effect.status in _MATERIAL_STATUSES and not effect.confirmed
    )