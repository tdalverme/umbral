"""Pure values for conversational trajectory evals v2.

Trajectories v2 are multi-turn acceptance cases with durable state snapshots,
question snapshots, turn effects, binding snapshots and verified target
context as evidence sources. Invariants are evaluated deterministically and
the release gate is strict (critical invariants 100%, success >=95%, family
>=90%, zero wrong-target mutations) per the published contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

TrajectoryInvariantId = Literal[
    "final_state_matches_expected",
    "no_repeated_answered_question",
    "no_unconfirmed_material_effect",
    "forbidden_bindings_are_non_computable",
    "no_wrong_target_mutation",
]

MANDATORY_INVARIANTS: tuple[str, ...] = (
    "final_state_matches_expected",
    "no_unconfirmed_material_effect",
    "forbidden_bindings_are_non_computable",
    "no_wrong_target_mutation",
)

KNOWN_INVARIANTS: frozenset[str] = frozenset(
    {
        "final_state_matches_expected",
        "no_repeated_answered_question",
        "no_unconfirmed_material_effect",
        "forbidden_bindings_are_non_computable",
        "no_wrong_target_mutation",
    }
)

KNOWN_ACT_KINDS: frozenset[str] = frozenset(
    {
        "resolve_pending",
        "create_radar",
        "set_filter",
        "clear_filter",
        "express_preference",
        "revise_preference",
        "withdraw_preference",
        "record_feedback",
        "query",
    }
)


@dataclass(frozen=True, slots=True)
class TrajectoryTurn:
    """One expected turn of a trajectory case."""

    user: str
    expected_acts: tuple[str, ...]
    expected_effects: tuple[str, ...]
    forbidden: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class TrajectoryCase:
    """One multi-turn acceptance case with its invariant set."""

    id: str
    family: str
    initial_state: Mapping[str, object]
    turns: tuple[TrajectoryTurn, ...]
    final_state: Mapping[str, object]
    invariants: tuple[str, ...]

    def requires(self, invariant_id: str) -> bool:
        return invariant_id in self.invariants


@dataclass(frozen=True, slots=True)
class TrajectoryDataset:
    """The versioned conversational-trajectory dataset."""

    contract_version: str
    registry_version: str
    cases: tuple[TrajectoryCase, ...]

    def case_by_id(self, case_id: str) -> TrajectoryCase | None:
        return next((case for case in self.cases if case.id == case_id), None)

    def cases_for_family(self, family: str) -> tuple[TrajectoryCase, ...]:
        return tuple(case for case in self.cases if case.family == family)


@dataclass(frozen=True, slots=True)
class DurableStateSnapshot:
    """One durable state snapshot recorded by the trajectory runner."""

    turn_index: int
    state: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class QuestionSnapshot:
    """A question the runner asked in a turn and the slot it targets."""

    turn_index: int
    slot: str
    answered: bool
    value: object | None = None


@dataclass(frozen=True, slots=True)
class TurnEffectRecord:
    """A durable effect the runner applied in a turn."""

    turn_index: int
    effect_key: str
    status: str
    confirmed: bool = False
    object_type: str | None = None
    object_id: str | None = None
    target_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class BindingSnapshot:
    """A binding snapshot the runner recorded for one turn."""

    turn_index: int
    kind: str
    matcher_type: str | None = None
    embedding_version_id: object | None = None
    confidence: float = 0.0
    mode: str = "soft"


@dataclass(frozen=True, slots=True)
class TrajectoryTrace:
    """Evidence collected while executing one trajectory case."""

    case_id: str
    durable_states: tuple[DurableStateSnapshot, ...] = field(default_factory=tuple)
    questions: tuple[QuestionSnapshot, ...] = field(default_factory=tuple)
    turn_effects: tuple[TurnEffectRecord, ...] = field(default_factory=tuple)
    bindings: tuple[BindingSnapshot, ...] = field(default_factory=tuple)
    verified_target_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class InvariantVerdict:
    """The deterministic verdict of one invariant for one case."""

    invariant_id: str
    case_id: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class TrajectoryCaseResult:
    """Per-case result: invariant verdicts and the case-level success flag."""

    case_id: str
    family: str
    invariant_verdicts: tuple[InvariantVerdict, ...]
    success: bool
    wrong_target_mutations: int = 0

    def passed(self, invariant_id: str) -> bool:
        return next(
            (
                verdict.passed
                for verdict in self.invariant_verdicts
                if verdict.invariant_id == invariant_id
            ),
            True,
        )


@dataclass(frozen=True, slots=True)
class TrajectorySuiteResult:
    """Aggregated result of one trajectory suite execution."""

    dataset_version: str
    case_results: tuple[TrajectoryCaseResult, ...]
    blocked: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def family_success(self, family: str) -> float:
        cases = [case for case in self.case_results if case.family == family]
        if not cases:
            return 0.0
        return sum(case.success for case in cases) / len(cases)


class TrajectoryEvalsError(Exception):
    """Base class for sanitized trajectory eval failures."""

    code = "trajectory_evals.error"


class TrajectoryValidationError(TrajectoryEvalsError):
    """A trajectory contract document violates its declared shape."""

    def __init__(self, error_codes: tuple[str, ...]) -> None:
        self.error_codes = error_codes
        self.code = "trajectory_evals.validation_failed"
        super().__init__(",".join(error_codes))


class TrajectoryGateBlocked(TrajectoryEvalsError):
    """The strict release gate blocks a trajectory suite."""

    code = "trajectory_evals.gate_blocked"

    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))