"""Immutable, closed contracts for the V5 conversation boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias
from uuid import UUID

from umbral.application.preferences.intensity import (
    PreferenceIntensity,
    PreferencePolarity,
)

FilterKeyV5: TypeAlias = Literal["budget_max", "zones", "min_rooms"]
FeedbackTypeV5: TypeAlias = Literal["like", "dislike", "save", "dismiss", "contacted"]
DecisionStatusV5: TypeAlias = Literal[
    "applied", "pending", "rejected", "needs_clarification"
]
OutcomeStatusV5: TypeAlias = DecisionStatusV5 | Literal["not_executed"]
FailureStageV5: TypeAlias = Literal[
    "context_failure",
    "interpretation_failure",
    "policy_failure",
    "execution_failure",
    "reply_failure",
    "provider_failure",
    "contract_or_fixture_failure",
]
FilterValueV5: TypeAlias = float | int | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceSpan:
    start: int
    end: int
    text: str

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < 0:
            raise ValueError("evidence span offsets must be non-negative")
        if self.end < self.start:
            raise ValueError("evidence span end must not precede start")


@dataclass(frozen=True, slots=True)
class UntrustedContentV5:
    source: str
    text: str
    may_supply_evidence: Literal[False] = False


@dataclass(frozen=True, slots=True)
class FocusedEntityV5:
    entity_ref: str


@dataclass(frozen=True, slots=True)
class PendingActionV5:
    pending_ref: str


@dataclass(frozen=True, slots=True)
class ConceptLinkV5:
    concept_ref: str
    confidence: float
    polarity: PreferencePolarity
    intensity: PreferenceIntensity
    evidence_spans: tuple[EvidenceSpan, ...] = ()
    force: Literal["soft"] = "soft"


@dataclass(frozen=True, slots=True)
class DesireViewV5:
    desire_ref: str
    raw_text: str
    subject_ref: str
    concept_links: tuple[ConceptLinkV5, ...] = ()


@dataclass(frozen=True, slots=True)
class HardFilterV5:
    filter_key: FilterKeyV5
    value: FilterValueV5
    force: Literal["hard"] = "hard"

    def __post_init__(self) -> None:
        _validate_filter_value(self.filter_key, self.value)


@dataclass(frozen=True, slots=True)
class TurnContextV5:
    user_id: str
    session_id: str
    active_radar_ref: str | None
    active_radar_version: int | None
    current_filters: tuple[HardFilterV5, ...]
    active_desires: tuple[DesireViewV5, ...]
    pending_action: PendingActionV5 | None
    focused_entity: FocusedEntityV5 | None
    verified_listing_refs: tuple[str, ...]
    allowed_capabilities: tuple[str, ...]
    untrusted_content: tuple[UntrustedContentV5, ...]
    context_schema_version: Literal["5"]
    correlation_id: str

    def authorizes(self, ref: str) -> bool:
        """Return whether this snapshot explicitly contains an opaque reference."""
        if ref == self.active_radar_ref:
            return True
        if ref in self.verified_listing_refs:
            return True
        if any(desire.desire_ref == ref for desire in self.active_desires):
            return True
        if self.pending_action is not None and ref == self.pending_action.pending_ref:
            return True
        return self.focused_entity is not None and ref == self.focused_entity.entity_ref


@dataclass(frozen=True, slots=True)
class CreateRadar:
    act_id: str
    confidence: float
    evidence_spans: tuple[EvidenceSpan, ...]
    name: str | None = None
    kind: Literal["create_radar"] = field(init=False, default="create_radar")


@dataclass(frozen=True, slots=True)
class SetFilter:
    act_id: str
    confidence: float
    evidence_spans: tuple[EvidenceSpan, ...]
    filter_key: FilterKeyV5
    value: FilterValueV5
    force: Literal["hard"] = field(init=False, default="hard")
    kind: Literal["set_filter"] = field(init=False, default="set_filter")

    def __post_init__(self) -> None:
        _validate_filter_value(self.filter_key, self.value)


@dataclass(frozen=True, slots=True)
class ClearFilter:
    act_id: str
    confidence: float
    evidence_spans: tuple[EvidenceSpan, ...]
    filter_key: FilterKeyV5
    kind: Literal["clear_filter"] = field(init=False, default="clear_filter")


@dataclass(frozen=True, slots=True)
class ExpressDesire:
    act_id: str
    confidence: float
    evidence_spans: tuple[EvidenceSpan, ...]
    raw_text: str
    subject_ref: str
    concept_links: tuple[ConceptLinkV5, ...] = ()
    kind: Literal["express_desire"] = field(init=False, default="express_desire")


@dataclass(frozen=True, slots=True)
class ReviseDesire:
    act_id: str
    confidence: float
    evidence_spans: tuple[EvidenceSpan, ...]
    desire_ref: str | None
    raw_text: str
    concept_links: tuple[ConceptLinkV5, ...] = ()
    kind: Literal["revise_desire"] = field(init=False, default="revise_desire")


@dataclass(frozen=True, slots=True)
class WithdrawDesire:
    act_id: str
    confidence: float
    evidence_spans: tuple[EvidenceSpan, ...]
    desire_ref: str | None
    kind: Literal["withdraw_desire"] = field(init=False, default="withdraw_desire")


@dataclass(frozen=True, slots=True)
class RecordFeedback:
    act_id: str
    confidence: float
    evidence_spans: tuple[EvidenceSpan, ...]
    listing_ref: str
    feedback_type: FeedbackTypeV5
    raw_text: str | None = None
    kind: Literal["record_feedback"] = field(init=False, default="record_feedback")


@dataclass(frozen=True, slots=True)
class ResolvePending:
    act_id: str
    confidence: float
    evidence_spans: tuple[EvidenceSpan, ...]
    pending_ref: str
    decision: Literal["approve", "reject"]
    kind: Literal["resolve_pending"] = field(init=False, default="resolve_pending")


@dataclass(frozen=True, slots=True)
class Query:
    act_id: str
    confidence: float
    evidence_spans: tuple[EvidenceSpan, ...]
    query_text: str
    kind: Literal["query"] = field(init=False, default="query")


@dataclass(frozen=True, slots=True)
class UnsupportedRequest:
    act_id: str
    confidence: float
    evidence_spans: tuple[EvidenceSpan, ...]
    request_text: str
    kind: Literal["unsupported_request"] = field(
        init=False, default="unsupported_request"
    )


ConversationActV5 = (
    CreateRadar | SetFilter | ClearFilter | ExpressDesire | ReviseDesire |
    WithdrawDesire | RecordFeedback | ResolvePending | Query |
    UnsupportedRequest
)


@dataclass(frozen=True, slots=True)
class TurnInterpretationV5:
    model_version: str
    prompt_version: str
    acts: tuple[ConversationActV5, ...]
    contract_version: Literal["5"] = "5"
    interpretation_version: Literal["conversation-interpretation-v5"] = (
        "conversation-interpretation-v5"
    )


@dataclass(frozen=True, slots=True)
class ActDecisionV5:
    act_id: str
    status: DecisionStatusV5
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class CreateRadarCommand:
    act_id: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class SetFilterCommand:
    act_id: str
    filter_key: FilterKeyV5
    value: FilterValueV5
    expected_profile_version: int | None = None


@dataclass(frozen=True, slots=True)
class ClearFilterCommand:
    act_id: str
    filter_key: FilterKeyV5
    expected_profile_version: int | None = None


@dataclass(frozen=True, slots=True)
class RecordDesireCommand:
    act_id: str
    raw_text: str
    subject_ref: str
    concept_links: tuple[ConceptLinkV5, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviseDesireCommand:
    act_id: str
    desire_ref: str
    raw_text: str
    concept_links: tuple[ConceptLinkV5, ...] = ()


@dataclass(frozen=True, slots=True)
class WithdrawDesireCommand:
    act_id: str
    desire_ref: str


@dataclass(frozen=True, slots=True)
class RecordFeedbackCommand:
    act_id: str
    listing_id: UUID
    feedback_type: FeedbackTypeV5
    raw_text: str | None = None


CommandV5 = (
    CreateRadarCommand
    | SetFilterCommand
    | ClearFilterCommand
    | RecordDesireCommand
    | ReviseDesireCommand
    | WithdrawDesireCommand
    | RecordFeedbackCommand
)


@dataclass(frozen=True, slots=True)
class TurnPlanV5:
    decisions: tuple[ActDecisionV5, ...]
    commands: tuple[CommandV5, ...] = ()

    def __post_init__(self) -> None:
        for command in self.commands:
            if not isinstance(
                command,
                (
                    CreateRadarCommand,
                    SetFilterCommand,
                    ClearFilterCommand,
                    RecordDesireCommand,
                    ReviseDesireCommand,
                    WithdrawDesireCommand,
                    RecordFeedbackCommand,
                ),
            ):
                raise ValueError(
                    "commands must be members of the closed command union"
                )


@dataclass(frozen=True, slots=True)
class ExecutedActV5:
    act_id: str
    effect_key: str
    status: OutcomeStatusV5 = "applied"
    object_ref: str | None = None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class ActOutcomeV5:
    act_id: str
    status: OutcomeStatusV5
    reason_code: str | None = None
    object_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ConversationTurnResultV5:
    context: TurnContextV5
    interpretation: TurnInterpretationV5 | None
    plan: TurnPlanV5 | None
    executed: tuple[ExecutedActV5, ...]
    outcomes: tuple[ActOutcomeV5, ...]
    failure_stage: FailureStageV5 | None = None


def _validate_filter_value(filter_key: FilterKeyV5, value: object) -> None:
    if filter_key == "budget_max":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("budget_max must be numeric")
        return
    if filter_key == "min_rooms":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("min_rooms must be an integer")
        return
    if filter_key != "zones":
        raise ValueError("filter key is not published")
    if (
        not isinstance(value, tuple)
        or len(value) > 15
        or not all(isinstance(zone, str) and zone for zone in value)
    ):
        raise ValueError("zones must be a tuple of strings")
