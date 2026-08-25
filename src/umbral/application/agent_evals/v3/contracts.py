"""Pure, versioned contracts for canonical agent evals v3."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from umbral.application.agent_evals.contracts import ModelCallCostRecord

SuiteKind = Literal["safety", "regression", "capability"]
Partition = Literal["development", "holdout"]
Risk = Literal["normal", "high", "critical"]
Fidelity = Literal["scripted", "managed"]
FailureKind = Literal[
    "product_failure",
    "safety_violation",
    "provider_failure",
    "harness_failure",
    "budget_exhausted",
]

KNOWN_SUITES = frozenset({"safety", "regression", "capability"})
KNOWN_PARTITIONS = frozenset({"development", "holdout"})
KNOWN_RISKS = frozenset({"normal", "high", "critical"})
KNOWN_INVARIANTS = frozenset(
    {
        "final_state_matches_expected",
        "no_repeated_answered_question",
        "no_unconfirmed_material_effect",
        "forbidden_bindings_are_non_computable",
        "no_wrong_target_mutation",
    }
)
KNOWN_ACTS = frozenset(
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
KNOWN_TOOLS = frozenset(
    {
        "get_search_profile",
        "propose_search_profile_update",
        "apply_search_profile_update",
        "find_matches",
        "explain_match",
        "compare_listings",
        "record_feedback",
        "search_urban_context",
        "propose_search_preference_update",
        "propose_search_preference_removal",
        "propose_learning_confirmation",
        "list_search_preferences",
        "get_listing_detail",
    }
)
KNOWN_PREDICATE_OPERATORS = frozenset(
    {
        "equals",
        "greater_than_initial",
        "less_than_initial",
        "in_verified_context",
        "in_allowed_values",
        "target_is_active_radar",
        "scope_equals",
    }
)


@dataclass(frozen=True, slots=True)
class ArgumentPredicate:
    source: Literal["act", "tool"]
    name: str
    path: str
    operator: Literal[
        "equals",
        "greater_than_initial",
        "less_than_initial",
        "in_verified_context",
        "in_allowed_values",
        "target_is_active_radar",
        "scope_equals",
    ]
    expected: object | None = None
    initial_path: str | None = None


@dataclass(frozen=True, slots=True)
class TurnExpectation:
    required_acts: tuple[str, ...]
    allowed_acts: tuple[str, ...]
    forbidden_acts: tuple[str, ...]
    required_tools: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    forbidden_tools: tuple[str, ...]
    argument_predicates: tuple[ArgumentPredicate, ...]
    required_effects: tuple[str, ...]
    forbidden_effects: tuple[str, ...]
    outcomes: tuple[str, ...]
    require_grounding: bool


@dataclass(frozen=True, slots=True)
class ScriptedTurn:
    interpretation: Mapping[str, object]
    reply: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class EvalTurn:
    user: str
    context: Mapping[str, object]
    script: ScriptedTurn
    expect: TurnExpectation


@dataclass(frozen=True, slots=True)
class CaseReview:
    reviewed_by: str
    reviewed_at: str
    rationale: str


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    suite: SuiteKind
    partition: Partition
    family: str
    risk: Risk
    initial_state: Mapping[str, object]
    turns: tuple[EvalTurn, ...]
    final_state: Mapping[str, object]
    invariants: tuple[str, ...]
    tags: tuple[str, ...]
    review: CaseReview


@dataclass(frozen=True, slots=True)
class EvalDataset:
    contract_version: str
    registry_version: str
    cases: tuple[EvalCase, ...]


@dataclass(frozen=True, slots=True)
class EvalPolicy:
    registry_version: str
    scripted_trials: int
    managed_normal_trials: int
    managed_critical_trials: int
    provider_retry_limit: int
    max_concurrency: int
    confidence_level: float
    review_sample_size: int
    max_reserved_cost_per_trial_usd: float


@dataclass(frozen=True, slots=True)
class EvalReleaseComponents:
    prompt_versions: tuple[str, ...]
    model_version: str
    state_schema_version: str
    topology_version: str
    interpretation_schema_version: str
    reply_schema_version: str
    tool_contract_version: str | None
    price_table_version: str


@dataclass(frozen=True, slots=True)
class EvalRelease:
    id: str
    components: EvalReleaseComponents
    owner: str
    justification: str
    activation: Mapping[str, object]
    date: str


@dataclass(frozen=True, slots=True)
class EvalReleases:
    contract_version: str
    registry_version: str
    releases: tuple[EvalRelease, ...]


@dataclass(frozen=True, slots=True)
class ObservedAct:
    kind: str
    target: Mapping[str, object]
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ObservedToolCall:
    name: str
    args: Mapping[str, object]
    status: str
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ObservedEffect:
    effect_key: str
    status: str
    object_type: str | None
    object_id: str | None
    reason_code: str | None
    detail: Mapping[str, object]
    confirmed: bool


@dataclass(frozen=True, slots=True)
class TurnTrace:
    turn_index: int
    acts: tuple[ObservedAct, ...]
    tools: tuple[ObservedToolCall, ...]
    effects: tuple[ObservedEffect, ...]
    refs: tuple[Mapping[str, str], ...]
    durable_state: Mapping[str, object]
    node_names: tuple[str, ...]
    outcome: str


@dataclass(frozen=True, slots=True)
class TrialTrace:
    case_id: str
    release_id: str
    trial_index: int
    attempt_index: int
    turns: tuple[TurnTrace, ...]
    verified_target_ids: frozenset[str]
    allowed_ref_ids: frozenset[tuple[str, str]]
    model_calls: tuple[ModelCallCostRecord, ...]
    latency_ms: int
    provider_error_code: str | None = None
    harness_error_code: str | None = None


@dataclass(frozen=True, slots=True)
class CheckResult:
    code: str
    passed: bool
    safety: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class TrialResult:
    case_id: str
    trial_index: int
    attempt_index: int
    safety_ok: bool
    quality_ok: bool
    failure_kind: FailureKind | None
    checks: tuple[CheckResult, ...]
    cost_usd: float
    trace: TrialTrace


@dataclass(frozen=True, slots=True)
class EvalBudget:
    cap_usd: float


@dataclass(frozen=True, slots=True)
class Interval:
    lower: float
    upper: float


@dataclass(frozen=True, slots=True)
class CaseAggregate:
    case_id: str
    family: str
    suite: SuiteKind
    risk: Risk
    successes: int
    trials: int
    success_rate: float
    all_trials_succeeded: bool
    interval: Interval
    safety_violations: int
    provider_failures: int
    product_failures: int
    average_cost_usd: float
    average_latency_ms: int


@dataclass(frozen=True, slots=True)
class SuiteRun:
    dataset_version: str
    policy_version: str
    release_id: str
    fidelity: Fidelity
    include_holdout: bool
    complete: bool
    trial_results: tuple[TrialResult, ...]
    case_aggregates: tuple[CaseAggregate, ...]
    failures: tuple[FailureKind, ...]
    total_cost_usd: float
    total_latency_ms: int


@dataclass(frozen=True, slots=True)
class CaseDelta:
    case_id: str
    baseline_successes: int
    baseline_trials: int
    candidate_successes: int
    candidate_trials: int
    success_rate_delta: float
    consistency_changed: bool
    cost_delta_usd: float
    latency_delta_ms: int
    regressed: bool


@dataclass(frozen=True, slots=True)
class ReviewItem:
    case_id: str
    reason: Literal["safety", "regression", "sample"]
    trial_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    baseline: SuiteRun
    candidate: SuiteRun
    deltas: tuple[CaseDelta, ...]
    review_items: tuple[ReviewItem, ...]
    blocked: bool
    approvable: bool
    reasons: tuple[str, ...]


class EvalV3ValidationError(Exception):
    """A v3 contract document violates its declared shape."""

    code = "agent_evals_v3.validation_failed"

    def __init__(self, error_codes: tuple[str, ...]) -> None:
        self.error_codes = error_codes
        super().__init__(",".join(error_codes))
