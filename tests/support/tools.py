"""Shared fakes for tool tests (H4.2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

from tests.support.agent import RecordingRunRecorder
from umbral.agent.tools.contracts import ToolResult
from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.agent.tools.tools import ToolServices, build_tool_implementations
from umbral.application.agent.tools.ports import SessionScope
from umbral.application.criteria.contracts import (
    Compilation,
    CompiledCriterion,
    PreferenceFact,
)
from umbral.application.feedback.contracts import (
    DecisionState,
    FeedbackEvent,
    FeedbackEventType,
    FeedbackRecord,
    LearningProposal,
    PreferenceImpact,
    ProposalChange,
)
from umbral.application.radar.contracts import (
    ListingDetail,
    MatchPage,
    RecommendationItem,
    RecommendationRun,
    SearchProfile,
)
from umbral.application.scoring.contracts import (
    Comparison,
    ComparisonCell,
    ComparisonDimension,
    Explanation,
    ExplanationReason,
    ExplanationRisk,
)
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract
from umbral.application.agent.tools.preferences import (
    load_preference_vocabulary,
)

USER_ID = UUID(int=1)
SESSION_ID = UUID(int=2)
PROFILE_ID = UUID(int=5)
CORRELATION_ID = UUID(int=9)
NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


class FakeRadar:
    def __init__(self, profile: SearchProfile | None = None) -> None:
        self.profile = profile or _profile()
        self.run = _run()
        self.items: tuple[RecommendationItem, ...] = (
            RecommendationItem(
                item_id=UUID(int=60),
                run_id=self.run.run_id,
                listing_id=UUID(int=70),
                score=0.9,
                position=1,
                contributions={},
            ),
            RecommendationItem(
                item_id=UUID(int=61),
                run_id=self.run.run_id,
                listing_id=UUID(int=71),
                score=0.7,
                position=2,
                contributions={},
            ),
        )
        self.listing_detail = _listing_detail()
        self.get_matches_calls = 0

    def get_profile(self, *, owner_id: UUID, profile_id: UUID) -> SearchProfile:
        return self.profile

    def validate_change(
        self, *, owner_id: UUID, profile_id: UUID, changes: Mapping[str, object]
    ) -> SearchProfile:
        return self.profile

    def update_profile(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        expected_version: int,
        changes: Mapping[str, object],
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> tuple[SearchProfile, RecommendationRun | None]:
        return self.profile, self.run

    def get_matches(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        run_id: UUID | None,
        after_position: int | None,
        limit: int,
        include_dismissed: bool = False,
    ) -> MatchPage:
        self.get_matches_calls += 1
        return MatchPage(
            run=self.run,
            items=self.items,
            next_after_position=None,
            points=(),
            summaries=(),
            decision_states={},
        )

    def latest_run_of(self, profile: SearchProfile) -> RecommendationRun | None:
        return self.run

    def get_listing_detail(self, owner_id: UUID, listing_id: UUID) -> ListingDetail:
        if listing_id != UUID(int=70):
            from umbral.application.radar.contracts import ListingNotAccessible

            raise ListingNotAccessible(listing_id)
        return self.listing_detail


class FakeScoring:
    def __init__(self) -> None:
        self.explanation = Explanation(
            search_profile_id=PROFILE_ID,
            run_id=UUID(int=50),
            listing_id=UUID(int=70),
            score_version="scoring-policy-v1",
            score=0.9,
            confidence=0.8,
            reasons=(
                ExplanationReason(
                    criterion_key="presupuesto",
                    state="match",
                    score=1.0,
                    confidence=1.0,
                    contribution=0.5,
                    evidence_level="strong",
                    reason_code="budget.within_range",
                    evidence_refs=({"kind": "observation", "id": "obs-1"},),
                    text="Dentro del presupuesto",
                ),
            ),
            risks=(
                ExplanationRisk(
                    criterion_key="ruido",
                    state="unknown",
                    reason_code="x",
                    text="Sin datos de ruido",
                ),
            ),
            missing_data=("ruido",),
            satisfied_filters=("presupuesto",),
            profile_snapshot={},
            feature_snapshot={},
        )
        self.comparison = Comparison(
            search_profile_id=PROFILE_ID,
            run_id=UUID(int=50),
            score_version="scoring-policy-v1",
            limit=6,
            listings=({},),
            dimensions=(
                ComparisonDimension(
                    kind="fixed", key="presupuesto", label="Presupuesto"
                ),
            ),
            cells=(
                ComparisonCell(
                    listing_id=UUID(int=70),
                    dimension_key="presupuesto",
                    value=100000.0,
                    state="match",
                    missing=False,
                ),
            ),
        )

    def get_explanation(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        run_id: UUID,
        listing_id: UUID,
    ) -> Explanation:
        return self.explanation

    def build_comparison(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        listing_ids: tuple[UUID, ...],
    ) -> Comparison:
        return self.comparison


class FakeFeedback:
    def __init__(self) -> None:
        self.calls: list[Mapping[str, object]] = []
        self.preference_calls: list[Mapping[str, object]] = []

    def record_feedback(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        listing_id: UUID,
        run_id: UUID | None,
        event_type: str,
        reason_keys: tuple[str, ...],
        idempotency_key: str,
        correlation_id: UUID,
        concept_feedback: tuple[Mapping[str, object], ...] = (),
        free_feedback: str | None = None,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> FeedbackRecord:
        self.calls.append(
            {
                "event_type": event_type,
                "reason_keys": reason_keys,
                "idempotency_key": idempotency_key,
                "concept_feedback": concept_feedback,
                "free_feedback": free_feedback,
            }
        )
        event = FeedbackEvent(
            event_id=UUID(int=80),
            profile_id=PROFILE_ID,
            listing_id=UUID(int=70),
            run_id=UUID(int=50),
            event_type=cast(FeedbackEventType, event_type),
            state="active",
            superseded_by=None,
            idempotency_key=idempotency_key,
            reasons=(),
            free_feedback=None,
            created_at=NOW,
            correlation_id=CORRELATION_ID,
        )
        return FeedbackRecord(
            event=event,
            decision_state=cast(DecisionState, event_type),
            superseded=False,
            noop=False,
            learning_proposal_id=(
                UUID(int=90) if event_type == "like" else None
            ),
        )

    def propose_preference(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        concept_key: str,
        polarity: str,
        value: str | None,
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> tuple[LearningProposal, PreferenceImpact]:
        self.preference_calls.append(
            {
                "profile_id": str(profile_id),
                "concept_key": concept_key,
                "polarity": polarity,
                "value": value,
                "correlation_id": str(correlation_id),
            }
        )
        change = ProposalChange(
            kind="preference_fact",
            concept_key=concept_key,
            polarity=polarity,
            suggested_weight=0.5,
            suggested_confidence=0.7,
            value=value,
        )
        proposal = LearningProposal(
            proposal_id=UUID(int=95),
            profile_id=profile_id,
            concept_id=UUID(int=96),
            concept_key=concept_key,
            policy_version_id=UUID(int=97),
            policy_version="1",
            change=change,
            prior_fact=None,
            evidence_refs=({"kind": "chat", "correlation_id": str(correlation_id)},),
            state="pending",
            expires_at=NOW,
            superseded_by=None,
            applied_profile_version_id=None,
            applied_run_id=None,
            created_at=NOW,
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        return proposal, PreferenceImpact(contradicts=False, current=None)

    def active_preferences(
        self, *, owner_id: UUID, profile_id: UUID
    ) -> tuple[PreferenceFact, ...]:
        return ()

    def get_proposal(
        self, *, owner_id: UUID, profile_id: UUID, proposal_id: UUID
    ) -> LearningProposal:
        change = ProposalChange(
            kind="preference_fact",
            concept_key="luminosidad",
            polarity="negative",
            suggested_weight=0.5,
            suggested_confidence=0.7,
            value=None,
        )
        return LearningProposal(
            proposal_id=proposal_id,
            profile_id=profile_id,
            concept_id=UUID(int=96),
            concept_key="luminosidad",
            policy_version_id=UUID(int=97),
            policy_version="1",
            change=change,
            prior_fact=None,
            evidence_refs=(),
            state="pending",
            expires_at=NOW,
            superseded_by=None,
            applied_profile_version_id=None,
            applied_run_id=None,
            created_at=NOW,
            correlation_id=UUID(int=9),
        )

    def propose_preference_removal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        concept_key: str,
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> tuple[LearningProposal, PreferenceImpact]:
        self.preference_calls.append(
            {
                "profile_id": str(profile_id),
                "concept_key": concept_key,
                "operation": "remove",
                "correlation_id": str(correlation_id),
            }
        )
        change = ProposalChange(
            kind="preference_fact",
            concept_key=concept_key,
            polarity="positive",
            suggested_weight=0.5,
            suggested_confidence=0.7,
            value=None,
        )
        proposal = LearningProposal(
            proposal_id=UUID(int=98),
            profile_id=profile_id,
            concept_id=UUID(int=96),
            concept_key=concept_key,
            policy_version_id=UUID(int=97),
            policy_version="1",
            change=change,
            prior_fact={"polarity": "positive", "fact_source": "chat"},
            evidence_refs=(
                {
                    "kind": "chat",
                    "operation": "remove",
                    "correlation_id": str(correlation_id),
                },
            ),
            state="pending",
            expires_at=NOW,
            superseded_by=None,
            applied_profile_version_id=None,
            applied_run_id=None,
            created_at=NOW,
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        return proposal, PreferenceImpact(
            contradicts=False,
            current={"concept_key": concept_key, "polarity": "positive"},
        )


class FakeCriteria:
    def __init__(self) -> None:
        self.compilation = Compilation(
            compilation_id=UUID(int=110),
            profile_id=PROFILE_ID,
            profile_version_id=UUID(int=120),
            compilation_version=1,
            criteria=(
                CompiledCriterion(
                    concept_key="presupuesto",
                    matcher_type="numeric_range",
                    params={"max": 150000},
                    source_ref="profile",
                    soft_to_hard=False,
                ),
            ),
            warnings=(),
            confirmations=(),
            created_at=NOW,
            correlation_id=CORRELATION_ID,
        )
        self.signals: tuple[Mapping[str, object], ...] = (
            {
                "signal_id": str(UUID(int=130)),
                "signal_type": "transporte",
                "signal_source": "osm",
                "observed_at": NOW.isoformat(),
                "algorithm_version": "v1",
                "payload": {"geometry": "POINT(1 2)"},
            },
        )

    def latest_compilation(self, profile_version_id: UUID) -> Compilation | None:
        return self.compilation

    def list_urban_signals(self, listing_id: UUID) -> tuple[Mapping[str, object], ...]:
        return self.signals


class _ProposalStub:
    def __getattr__(self, _name: str) -> Any:
        raise AssertionError("proposal tools should not be exercised in read tests")


@dataclass(slots=True)
class FakeServices:
    radar: FakeRadar = field(default_factory=FakeRadar)
    scoring: FakeScoring = field(default_factory=FakeScoring)
    feedback: FakeFeedback = field(default_factory=FakeFeedback)
    criteria: FakeCriteria = field(default_factory=FakeCriteria)
    proposals: object = field(default_factory=_ProposalStub)


class FakeScopeReader:
    def __init__(self, scope: SessionScope | None = None) -> None:
        self.scope = scope

    def read_scope(self, user_id: UUID, session_id: UUID) -> SessionScope | None:
        return self.scope


def build_executor(
    services: FakeServices | None = None,
    *,
    scope: SessionScope | None = None,
    deny_scope: bool = False,
) -> tuple[ToolExecutor, FakeServices]:
    active_services = services or FakeServices()
    resolved_scope = (
        None
        if deny_scope
        else (
            scope
            or SessionScope(
                session_id=SESSION_ID,
                search_profile_id=PROFILE_ID,
                status="active",
            )
        )
    )
    executor = ToolExecutor(
        registry=ToolRegistry(load_tool_contract),
        implementations=build_tool_implementations(
            ToolServices(
                radar=active_services.radar,
                scoring=active_services.scoring,
                feedback=active_services.feedback,
                criteria=active_services.criteria,
                proposals=active_services.proposals,  # type: ignore[arg-type]
                vocabulary=load_preference_vocabulary(),
            )
        ),
        recorder=RecordingRunRecorder(),
        scope_reader=FakeScopeReader(resolved_scope),
        timeout_seconds=1.0,
    )
    return executor, active_services


def call_tool(
    executor: ToolExecutor,
    name: str,
    args: Mapping[str, object] | None = None,
) -> ToolResult:
    return executor.execute(
        user_id=USER_ID,
        session_id=SESSION_ID,
        run_id=UUID(int=10),
        correlation_id=CORRELATION_ID,
        name=name,
        args=args or {},
    )


def payload(result: ToolResult) -> Mapping[str, Any]:
    """Return the redacted tool payload, asserting the call succeeded."""
    assert result.status == "ok", result.error_code
    assert result.result is not None
    return result.result


def _profile() -> SearchProfile:
    return SearchProfile(
        profile_id=PROFILE_ID,
        owner_id=USER_ID,
        name="radar",
        operation="rental",
        zones=("palermo",),
        budget_max=150000,
        budget_min=None,
        min_rooms=2,
        surface_min=None,
        surface_max=None,
        status="active",
        unknown_strategy={},
        version=3,
        current_version_id=UUID(int=120),
        latest_run_id=UUID(int=50),
        created_at=NOW,
        updated_at=NOW,
        correlation_id=CORRELATION_ID,
        actor_kind="service",
        actor_id=None,
    )


def _run() -> RecommendationRun:
    return RecommendationRun(
        run_id=UUID(int=50),
        profile_id=PROFILE_ID,
        profile_version_id=UUID(int=120),
        state="succeeded",
        trigger="edited",
        score_policy_version="scoring-policy-v1",
        candidate_count=10,
        published_item_count=2,
        failure_code=None,
        job_execution_id=None,
        created_at=NOW,
        finished_at=NOW,
        correlation_id=CORRELATION_ID,
        actor_kind="service",
        actor_id=None,
    )


def _listing_detail() -> ListingDetail:
    return ListingDetail(
        listing_id=UUID(int=70),
        source_id="src-1",
        url="https://src.invalid/70",
        neighborhood="Palermo",
        geo_precision="block",
        total_cost=100000.0,
        price_value=100000.0,
        price_currency="ARS",
        expenses_value=None,
        surface_m2=55.0,
        rooms=2,
        bedrooms=None,
        floor=None,
        property_type="departamento",
        amenities=(),
        description_text=None,
        normalization_errors=(),
        known_changes=(),
    )
