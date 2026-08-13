"""Pure, transport-independent values and errors for agent evals.

This module is harness machinery (research R-07): it is never imported by the
API or workers at runtime. The eval runner derives metrics from persisted run
records, never from free text (R-04).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

Family = Literal[
    "onboarding",
    "ambiguous_change",
    "explanation",
    "comparison",
    "feedback",
    "injection",
    "safe_refusal",
]

Outcome = Literal["completed", "clarification", "safe_refusal", "failed"]

EvalVerdict = Literal[
    "ok",
    "tool_selection_change",
    "args_change",
    "grounding_change",
    "confirmation_change",
    "outcome_change",
    "cost_delta",
    "latency_delta",
]

GatewayFidelity = Literal["simulated", "real"]

KNOWN_FAMILIES: frozenset[str] = frozenset(
    {
        "onboarding",
        "ambiguous_change",
        "explanation",
        "comparison",
        "feedback",
        "injection",
        "safe_refusal",
        "preferences",
    }
)
KNOWN_OUTCOMES: frozenset[str] = frozenset(
    {"completed", "clarification", "safe_refusal", "failed"}
)
KNOWN_TOOLS: frozenset[str] = frozenset(
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


@dataclass(frozen=True, slots=True)
class GoldenToolCallExpectation:
    """The expected tool call for one golden conversation case."""

    tool: str
    args: Mapping[str, object]
    requires_confirmation: bool
    order: int


@dataclass(frozen=True, slots=True)
class GroundingExpectation:
    """Expected grounding constraints of a golden case reply."""

    require_refs: bool
    min_refs: int
    declare_missing: bool


@dataclass(frozen=True, slots=True)
class GoldenConversationCase:
    """One curated conversation case with its expected behavior."""

    id: str
    family: str
    context: Mapping[str, object]
    turns: tuple[str, ...]
    expectation: GoldenExpectation
    tags: tuple[str, ...] = field(default_factory=tuple)
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class GoldenExpectation:
    """Expected behavior of one golden conversation case."""

    tool_calls: tuple[GoldenToolCallExpectation, ...]
    grounding: GroundingExpectation
    outcome: Outcome


@dataclass(frozen=True, slots=True)
class GoldenDataset:
    """The versioned, product-reviewed golden conversation dataset."""

    contract_version: str
    registry_version: str
    reviewed_by: str
    reviewed_at: str
    min_cases_per_family: int
    cases: tuple[GoldenConversationCase, ...]

    def case_by_id(self, case_id: str) -> GoldenConversationCase | None:
        return next((case for case in self.cases if case.id == case_id), None)

    def cases_for_family(self, family: str) -> tuple[GoldenConversationCase, ...]:
        return tuple(case for case in self.cases if case.family == family)


@dataclass(frozen=True, slots=True)
class ReleaseComponents:
    """The versioned components a graph release bundles."""

    prompt_versions: tuple[str, ...]
    model_version: str
    state_schema_version: str
    topology_version: str
    intent_schema_version: str
    price_table_version: str
    touches_prompts_or_model: bool


@dataclass(frozen=True, slots=True)
class ReleaseActivation:
    """Activation state of a graph release (hybrid rule, clarification Q6)."""

    status: Literal["pending", "active", "reverted"]
    approved_by: str | None
    approval_evidence: str | None
    reverted_reason: str | None


@dataclass(frozen=True, slots=True)
class GraphRelease:
    """One immutable, versioned release of the graph."""

    id: str
    components: ReleaseComponents
    owner: str
    justification: str
    affected_case_ids: tuple[str, ...]
    activation: ReleaseActivation
    date: str


@dataclass(frozen=True, slots=True)
class GraphReleases:
    """Append-only registry of graph releases."""

    contract_version: str
    registry_version: str
    releases: tuple[GraphRelease, ...]

    def active_release(self) -> GraphRelease | None:
        return next(
            (
                release
                for release in self.releases
                if release.activation.status == "active"
            ),
            None,
        )

    def by_id(self, release_id: str) -> GraphRelease | None:
        return next(
            (release for release in self.releases if release.id == release_id),
            None,
        )

    def affected_for(self, release_id: str) -> frozenset[str]:
        return frozenset(
            case_id
            for release in self.releases
            if release.id == release_id
            for case_id in release.affected_case_ids
        )


@dataclass(frozen=True, slots=True)
class PriceTableEntry:
    """One model price row of the price table contract."""

    model_version: str
    price_input_per_1k: float
    price_output_per_1k: float


@dataclass(frozen=True, slots=True)
class PriceTable:
    """Versioned model price table used to derive eval/budget cost."""

    contract_version: str
    registry_version: str
    currency: str
    entries: tuple[PriceTableEntry, ...]

    def price_for(self, model_version: str) -> PriceTableEntry | None:
        return next(
            (entry for entry in self.entries if entry.model_version == model_version),
            None,
        )


@dataclass(frozen=True, slots=True)
class ModelCallCostRecord:
    """Token usage record of one model call (pure slice of the run record)."""

    model_version: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class RecordedToolCall:
    """One executed tool call recorded by a graph run (research R-04)."""

    name: str
    status: str
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class CaseTrace:
    """Behavioral trace of one golden case execution, derived from records."""

    case_id: str
    run_status: str
    intent: str | None
    clarification_pending: bool
    tool_calls: tuple[RecordedToolCall, ...]
    model_calls: tuple[ModelCallCostRecord, ...]
    latency_ms: int
    refs: tuple[Mapping[str, object], ...]
    allowed_ref_ids: frozenset[tuple[str, str]] = frozenset()


@dataclass(frozen=True, slots=True)
class CaseEvalResult:
    """Per-case metrics and gate verdict of an eval suite."""

    case_id: str
    tool_selection_ok: bool
    args_valid: bool
    grounding_ok: bool
    confirmation_ok: bool
    outcome_ok: bool
    cost_usd: float
    latency_ms: int
    verdict: EvalVerdict
    reason: str = ""


@dataclass(frozen=True, slots=True)
class EvalSuiteReport:
    """Result of one eval suite over the golden dataset."""

    dataset_version: str
    baseline_release_id: str
    candidate_release_id: str | None
    gateway_fidelity: GatewayFidelity
    metrics: Mapping[str, float]
    case_results: tuple[CaseEvalResult, ...]
    blocked: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


class AgentEvalsError(Exception):
    """Base class for sanitized agent evals failures."""

    code = "agent_evals.error"


class AgentEvalsValidationError(AgentEvalsError):
    """An agent evals contract document violates its declared shape."""

    def __init__(self, error_codes: tuple[str, ...]) -> None:
        self.error_codes = error_codes
        self.code = "agent_evals.validation_failed"
        super().__init__(",".join(error_codes))


class AgentEvalsBlocked(AgentEvalsError):
    """The regression gate blocks an unexplained graph release change."""

    code = "agent_evals.regression_blocked"

    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))
