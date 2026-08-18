"""Pure parsing and validation of the trajectory dataset v2 contract.

The dataset (``contracts/agent-evals/v2/conversation-trajectories-v2.schema.json``)
declares per-case invariants; every case must include the mandatory invariant
set so a 100% critical gate is meaningful. Validation rejects unknown
invariants, act kinds, malformed turns and duplicate case ids.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from umbral.application.agent_evals.trajectories.contracts import (
    KNOWN_ACT_KINDS,
    KNOWN_INVARIANTS,
    MANDATORY_INVARIANTS,
    TrajectoryCase,
    TrajectoryDataset,
    TrajectoryTurn,
    TrajectoryValidationError,
)


def load_trajectory_dataset(path: Path) -> TrajectoryDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise TrajectoryValidationError(("trajectory_evals.dataset_required",))
    return parse_trajectory_dataset(raw)


def parse_trajectory_dataset(
    data: Mapping[str, object],
) -> TrajectoryDataset:
    errors: list[str] = []
    if data.get("contract_version") != "2":
        errors.append("trajectory_evals.unsupported_contract_version")
    if data.get("registry_version") != "conversation-trajectories-v2":
        errors.append("trajectory_evals.registry_version_required")
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        errors.append("trajectory_evals.cases_required")
        raw_cases = []
    cases: list[TrajectoryCase] = []
    seen_ids: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, Mapping):
            errors.append("trajectory_evals.case_invalid_shape")
            continue
        case, case_errors = _parse_case(raw)
        if case_errors:
            errors.extend(case_errors)
            continue
        if case.id in seen_ids:
            errors.append(f"trajectory_evals.duplicate_case:{case.id}")
        seen_ids.add(case.id)
        cases.append(case)
    if errors:
        raise TrajectoryValidationError(tuple(sorted(set(errors))))
    return TrajectoryDataset(
        contract_version="2",
        registry_version=str(
        data.get("registry_version") or "conversation-trajectories-v2"
    ),
        cases=tuple(cases),
    )


def _parse_case(
    raw: Mapping[str, object],
) -> tuple[TrajectoryCase, list[str]]:
    errors: list[str] = []
    case_id = _required_str(raw.get("id"), errors, "id")
    family = _required_str(raw.get("family"), errors, "family")
    initial = raw.get("initial_state")
    if not isinstance(initial, Mapping):
        errors.append("trajectory_evals.initial_state_required")
        initial = {}
    final = raw.get("final_state")
    if not isinstance(final, Mapping):
        errors.append("trajectory_evals.final_state_required")
        final = {}
    raw_turns = raw.get("turns")
    if not isinstance(raw_turns, list) or not raw_turns:
        errors.append("trajectory_evals.turns_required")
        raw_turns = []
    turns: list[TrajectoryTurn] = []
    for raw_turn in raw_turns:
        if not isinstance(raw_turn, Mapping):
            errors.append("trajectory_evals.turn_invalid_shape")
            continue
        turn, turn_errors = _parse_turn(raw_turn)
        if turn_errors:
            errors.extend(turn_errors)
            continue
        turns.append(turn)
    raw_invariants = raw.get("invariants")
    if not isinstance(raw_invariants, list) or not raw_invariants:
        errors.append("trajectory_evals.invariants_required")
        raw_invariants = []
    invariants: list[str] = []
    for item in raw_invariants:
        if not isinstance(item, str):
            errors.append("trajectory_evals.invariant_invalid")
            continue
        if item not in KNOWN_INVARIANTS:
            errors.append(f"trajectory_evals.unknown_invariant:{item}")
            continue
        if item in invariants:
            errors.append(f"trajectory_evals.duplicate_invariant:{item}")
            continue
        invariants.append(item)
    for mandatory in MANDATORY_INVARIANTS:
        if mandatory not in invariants:
            errors.append(f"trajectory_evals.missing_mandatory:{mandatory}")
    return (
        TrajectoryCase(
            id=case_id or "",
            family=family or "",
            initial_state=dict(initial),
            turns=tuple(turns),
            final_state=dict(final),
            invariants=tuple(invariants),
        ),
        errors,
    )


def _parse_turn(raw: Mapping[str, object]) -> tuple[TrajectoryTurn, list[str]]:
    errors: list[str] = []
    user = raw.get("user")
    if not isinstance(user, str) or not user:
        errors.append("trajectory_evals.turn_user_required")
    raw_acts = raw.get("expected_acts")
    if not isinstance(raw_acts, list) or not raw_acts:
        errors.append("trajectory_evals.turn_acts_required")
        raw_acts = []
    acts: list[str] = []
    for item in raw_acts:
        if not isinstance(item, str):
            errors.append("trajectory_evals.turn_act_invalid")
            continue
        if item not in KNOWN_ACT_KINDS:
            errors.append(f"trajectory_evals.unknown_act:{item}")
            continue
        acts.append(item)
    raw_effects = raw.get("expected_effects")
    effects = (
        tuple(str(item) for item in raw_effects)
        if isinstance(raw_effects, list)
        else ()
    )
    if not effects:
        errors.append("trajectory_evals.turn_effects_required")
    raw_forbidden = raw.get("forbidden")
    forbidden = (
        tuple(str(item) for item in raw_forbidden)
        if isinstance(raw_forbidden, list)
        else ()
    )
    return (
        TrajectoryTurn(
            user=str(user or ""),
            expected_acts=tuple(acts),
            expected_effects=effects,
            forbidden=forbidden,
        ),
        errors,
    )


def _required_str(value: object, errors: list[str], field: str) -> str:
    if not isinstance(value, str) or not value:
        errors.append(f"trajectory_evals.{field}_required")
        return ""
    return value