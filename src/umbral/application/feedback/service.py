"""Orchestration for immutable feedback and controlled learning (H3.3).

The service owns the append-only feedback event chain with an idempotent,
compensation-linked supersede, the shared shortlist persistence, the
deterministic learning proposal lifecycle (created from reasoned signals,
never auto-applied), and the confirm/undo flows that orchestrate the existing
criteria and radar seams. Direct feedback never creates runs (FR-015).
"""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from umbral.application.criteria.contracts import PreferenceFact
from umbral.application.criteria.service import CriteriaService
from umbral.application.events.contracts import ProductEvent
from umbral.application.events.registry import EventsRegistrySpec, event_version
from umbral.application.feedback.contracts import (
    ConfirmationResult,
    DecisionItem,
    DecisionStateRow,
    FeedbackEvent,
    FeedbackInvalidReason,
    FeedbackNotAccessible,
    FeedbackNotFound,
    FeedbackRecord,
    FeedbackStateError,
    FeedbackTerminal,
    FeedbackValidationError,
    LearningPolicyDoc,
    LearningPolicyVersion,
    LearningProposal,
    ProposalChange,
    ProposalNotConfirmed,
    ProposalNotFound,
    ProposalNotPending,
    QuickReasonsSpec,
    ReasonRef,
    is_event_type,
    is_polarity,
)
from umbral.application.feedback.policy import parse_learning_policy
from umbral.application.feedback.ports import (
    ConceptReader,
    EventWriter,
    FactReader,
    FeedbackEventRepository,
    LearningPolicyRepository,
    LearningProposalRepository,
    ListingReader,
    ProfileReader,
    ShortlistPort,
)
from umbral.application.feedback.signals import Signal, evaluate_signals
from umbral.application.radar.contracts import SearchProfile
from umbral.application.radar.service import RadarService

Clock = Callable[[], datetime]

_EVENT_POLARITY = {"like": "positive", "dislike": "negative"}
_FACT_SOURCE_CONFIRM = "learning.proposal"
_FACT_SOURCE_UNDO = "learning.undo"
_SIGNAL_TYPES = frozenset({"like", "dislike"})


class FeedbackService:
    def __init__(
        self,
        *,
        events: FeedbackEventRepository,
        policies: LearningPolicyRepository,
        proposals: LearningProposalRepository,
        shortlists: ShortlistPort,
        profiles: ProfileReader,
        listings: ListingReader,
        concepts: ConceptReader,
        facts: FactReader,
        events_out: EventWriter,
        events_registry: EventsRegistrySpec,
        reasons: QuickReasonsSpec,
        policy_seed: Mapping[str, object],
        policy_seed_version: str,
        free_feedback_enabled: bool = False,
        max_free_feedback_length: int = 500,
        radar: RadarService | None = None,
        criteria: CriteriaService | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.events = events
        self.policies = policies
        self.proposals = proposals
        self.shortlists = shortlists
        self.profiles = profiles
        self.listings = listings
        self.concepts = concepts
        self.facts = facts
        self.events_out = events_out
        self.events_registry = events_registry
        self.reasons = reasons
        self.policy_seed = dict(policy_seed)
        self.policy_seed_version = policy_seed_version
        self.free_feedback_enabled = free_feedback_enabled
        self.max_free_feedback_length = max_free_feedback_length
        self.radar = radar
        self.criteria = criteria
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Feedback recording (US1, US2)
    # ------------------------------------------------------------------

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
        free_feedback: str | None = None,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> FeedbackRecord:
        profile = self._owned(owner_id, profile_id)
        if not is_event_type(event_type):
            raise FeedbackValidationError((f"feedback.invalid_event_type:{event_type}",))
        if not idempotency_key or len(idempotency_key) > 200:
            raise FeedbackValidationError(("feedback.invalid_idempotency_key",))
        existing = self.events.get_by_idempotency(profile_id, idempotency_key)
        if existing is not None:
            return FeedbackRecord(
                event=existing,
                decision_state=existing.event_type,
                superseded=False,
                noop=True,
            )
        reason_refs = self._validate_reasons(event_type, reason_keys)
        free_feedback = self._validate_free_feedback(free_feedback)
        active = self.events.active_state(profile_id, listing_id)
        superseded_event: FeedbackEvent | None = active
        if active is not None and active.event_type == "contacted":
            raise FeedbackTerminal("contacted listings accept no further feedback")
        if active is not None and active.event_type == event_type:
            return FeedbackRecord(
                event=active,
                decision_state=active.event_type,
                superseded=False,
                noop=True,
            )
        now = self.clock()
        event = FeedbackEvent(
            event_id=uuid4(),
            profile_id=profile_id,
            listing_id=listing_id,
            run_id=run_id,
            event_type=event_type,  # type: ignore[arg-type]
            state="active",
            superseded_by=active.event_id if active is not None else None,
            idempotency_key=idempotency_key,
            reasons=reason_refs,
            free_feedback=free_feedback,
            created_at=now,
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        stored = self.events.record(event, superseded=superseded_event)
        self._apply_shortlist(event_type, superseded_event, profile_id, listing_id, now)
        superseded = superseded_event is not None
        self._emit_server_event(
            event_type="feedback.recorded.v1",
            correlation_id=correlation_id,
            actor_id=actor_id,
            payload={
                "feedback_event_id": str(stored.event_id),
                "search_profile_id": str(profile_id),
                "listing_id": str(listing_id),
                "event_type": stored.event_type,
                "decision_state": stored.event_type,
                "superseded": superseded,
                "reason_count": len(reason_refs),
                "has_free_feedback": free_feedback is not None,
            },
        )
        if stored.event_type in _SIGNAL_TYPES:
            learning_proposal_id = self._evaluate_learning(
                profile=profile,
                event=stored,
                correlation_id=correlation_id,
                actor_kind=actor_kind,
                actor_id=actor_id,
            )
        else:
            learning_proposal_id = None
        return FeedbackRecord(
            event=stored,
            decision_state=stored.event_type,
            superseded=superseded,
            noop=False,
            learning_proposal_id=learning_proposal_id,
        )

    def decision_state(
        self, *, owner_id: UUID, profile_id: UUID, listing_id: UUID
    ) -> DecisionStateRow:
        self._owned(owner_id, profile_id)
        active = self.events.active_state(profile_id, listing_id)
        if active is None:
            return DecisionStateRow(decision_state="none", event_id=None, event_type=None, created_at=None)
        return DecisionStateRow(
            decision_state=active.event_type,
            event_id=active.event_id,
            event_type=active.event_type,
            created_at=active.created_at,
        )

    def decision_states(
        self, *, owner_id: UUID, profile_id: UUID, listing_ids: tuple[UUID, ...]
    ) -> Mapping[UUID, str]:
        self._owned(owner_id, profile_id)
        if not listing_ids:
            return {}
        active = self.events.active_for_profile(profile_id)
        return {
            event.listing_id: event.event_type
            for event in active
            if event.listing_id in listing_ids
        }

    def list_decision_items(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        decision_state: str | None,
        after: int | None,
        limit: int,
    ) -> tuple[tuple[DecisionItem, ...], int | None]:
        self._owned(owner_id, profile_id)
        if decision_state is not None and not is_event_type(decision_state):
            raise FeedbackValidationError((f"feedback.invalid_state:{decision_state}",))
        events, next_after = self.events.list_for_profile(
            profile_id, decision_state, after, limit
        )
        items: list[DecisionItem] = []
        for event in events:
            listing = self.listings.get(event.listing_id)
            items.append(
                DecisionItem(
                    listing_id=event.listing_id,
                    decision_state=event.event_type,
                    event_id=event.event_id,
                    event_type=event.event_type,
                    reason_keys=tuple(reason.reason_key for reason in event.reasons),
                    created_at=event.created_at,
                    summary=listing,
                )
            )
        return tuple(items), next_after

    # ------------------------------------------------------------------
    # Learning proposals (US3, US4, US5)
    # ------------------------------------------------------------------

    def seed_policy_registry(self, correlation_id: UUID) -> int:
        if self.policies.latest_version(self.policy_seed_version) is not None:
            return 0
        self.register_policy_version(
            policy_key=self.policy_seed_version,
            payload=self.policy_seed,
            correlation_id=correlation_id,
        )
        return 1

    def register_policy_version(
        self, *, policy_key: str, payload: Mapping[str, object], correlation_id: UUID
    ) -> LearningPolicyVersion:
        parsed = parse_learning_policy(payload)
        latest = self.policies.latest_version(policy_key)
        policy_version = (latest.policy_version + 1) if latest is not None else 1
        return self.policies.register_version(
            policy_key=policy_key,
            policy_version=policy_version,
            contract_version=parsed.contract_version,
            payload=dict(payload),
            correlation_id=correlation_id,
            now=self.clock(),
        )

    def latest_learning_document(self) -> LearningPolicyDoc:
        version = self.policies.latest_version(self.policy_seed_version)
        if version is None:
            self.seed_policy_registry(uuid4())
            version = self.policies.latest_version(self.policy_seed_version)
        if version is None:
            raise FeedbackNotFound(
                f"no learning policy registered: {self.policy_seed_version}"
            )
        return parse_learning_policy(version.payload)

    def list_proposals(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        state: str | None,
        after: int | None,
        limit: int,
    ) -> tuple[tuple[LearningProposal, ...], int | None]:
        self._owned(owner_id, profile_id)
        proposals, next_after = self.proposals.list_for_profile(
            profile_id, state, after, limit
        )
        expired = self._expire_overdue(proposals)
        items = tuple(item for item in proposals if item.proposal_id not in expired)
        return items, next_after

    def get_proposal(
        self, *, owner_id: UUID, profile_id: UUID, proposal_id: UUID
    ) -> LearningProposal:
        self._owned(owner_id, profile_id)
        proposal = self._owned_proposal(profile_id, proposal_id)
        if proposal.state == "pending":
            proposal = self._expire_if_overdue(proposal)
        return proposal

    def confirm_proposal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        proposal_id: UUID,
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> ConfirmationResult:
        self._owned(owner_id, profile_id)
        proposal = self._owned_proposal(profile_id, proposal_id)
        if proposal.state == "pending":
            proposal = self._expire_if_overdue(proposal)
        if proposal.state != "pending":
            raise ProposalNotPending(f"proposal is {proposal.state}")
        if self.radar is None or self.criteria is None:
            raise FeedbackStateError("learning confirm is not available")
        change = proposal.change
        fact = self._active_fact(profile_id, change.concept_key)
        prior_fact = (
            {
                "value": fact.value,
                "weight": fact.weight,
                "polarity": fact.polarity,
                "confidence": fact.confidence,
            }
            if fact is not None
            else {"exists": False}
        )
        self.criteria.record_preference_fact(
            owner_id=owner_id,
            profile_id=profile_id,
            concept_key=change.concept_key,
            value=change.value,
            weight=change.suggested_weight,
            polarity=change.polarity,
            confidence=change.suggested_confidence,
            fact_source=_FACT_SOURCE_CONFIRM,
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        updated_profile, version = self.radar.bump_profile_version(
            owner_id=owner_id,
            profile_id=profile_id,
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        self.criteria.compile_profile(
            owner_id=owner_id,
            profile_id=profile_id,
            profile_version_id=version.version_id,
            edits=(),
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        run = self.radar.submit_run(profile=updated_profile, version=version)
        confirmed = self.proposals.update(
            _with_state(
                proposal,
                state="confirmed",
                prior_fact=prior_fact,
                applied_profile_version_id=version.version_id,
                applied_run_id=run.run_id if run is not None else None,
            )
        )
        self._emit_server_event(
            event_type="learning.proposal_confirmed.v1",
            correlation_id=correlation_id,
            actor_id=actor_id,
            payload={
                "proposal_id": str(proposal.proposal_id),
                "search_profile_id": str(profile_id),
                "concept_key": change.concept_key,
                "applied_profile_version": version.profile_version,
                "run_id": str(run.run_id) if run is not None else "",
            },
        )
        return ConfirmationResult(
            proposal=confirmed,
            applied_profile_version=version.profile_version,
            run_id=run.run_id if run is not None else None,
        )

    def reject_proposal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        proposal_id: UUID,
        correlation_id: UUID,
        actor_id: str | None = None,
    ) -> LearningProposal:
        self._owned(owner_id, profile_id)
        proposal = self._owned_proposal(profile_id, proposal_id)
        if proposal.state == "pending":
            proposal = self._expire_if_overdue(proposal)
        if proposal.state != "pending":
            raise ProposalNotPending(f"proposal is {proposal.state}")
        updated = self.proposals.update(_with_state(proposal, state="rejected"))
        self._emit_server_event(
            event_type="learning.proposal_rejected.v1",
            correlation_id=correlation_id,
            actor_id=actor_id,
            payload={
                "proposal_id": str(proposal.proposal_id),
                "search_profile_id": str(profile_id),
            },
        )
        return updated

    def expand_proposal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        proposal_id: UUID,
        change: ProposalChange,
        correlation_id: UUID,
        actor_id: str | None = None,
    ) -> LearningProposal:
        self._owned(owner_id, profile_id)
        proposal = self._owned_proposal(profile_id, proposal_id)
        if proposal.state == "pending":
            proposal = self._expire_if_overdue(proposal)
        if proposal.state != "pending":
            raise ProposalNotPending(f"proposal is {proposal.state}")
        self._validate_change(change)
        updated = self.proposals.update(_with_change(proposal, change))
        self._emit_server_event(
            event_type="learning.proposal_expanded.v1",
            correlation_id=correlation_id,
            actor_id=actor_id,
            payload={
                "proposal_id": str(proposal.proposal_id),
                "search_profile_id": str(profile_id),
            },
        )
        return updated

    def undo_proposal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        proposal_id: UUID,
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> LearningProposal:
        self._owned(owner_id, profile_id)
        proposal = self._owned_proposal(profile_id, proposal_id)
        if proposal.state != "confirmed":
            raise ProposalNotConfirmed(f"proposal is {proposal.state}")
        prior = proposal.prior_fact
        if prior is None:
            raise FeedbackStateError("no prior fact recorded for undo")
        if self.radar is None or self.criteria is None:
            raise FeedbackStateError("learning undo is not available")
        change = proposal.change
        existed = prior.get("exists", True) is not False
        prior_value = prior.get("value")
        prior_weight = (
            _as_float(prior.get("weight"), 0.0) if existed else 0.0
        )
        prior_polarity = (
            str(prior.get("polarity", "negative")) if existed else "negative"
        )
        prior_confidence = (
            _as_float(prior.get("confidence"), 0.0) if existed else 0.0
        )
        self.criteria.record_preference_fact(
            owner_id=owner_id,
            profile_id=profile_id,
            concept_key=change.concept_key,
            value=prior_value,
            weight=prior_weight,
            polarity=prior_polarity,
            confidence=prior_confidence,
            fact_source=_FACT_SOURCE_UNDO,
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        updated_profile, version = self.radar.bump_profile_version(
            owner_id=owner_id,
            profile_id=profile_id,
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        self.criteria.compile_profile(
            owner_id=owner_id,
            profile_id=profile_id,
            profile_version_id=version.version_id,
            edits=(),
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        run = self.radar.submit_run(profile=updated_profile, version=version)
        updated = self.proposals.update(
            _with_state(
                proposal,
                state="superseded",
                applied_profile_version_id=version.version_id,
                applied_run_id=run.run_id if run is not None else None,
            )
        )
        self._emit_server_event(
            event_type="learning.proposal_undone.v1",
            correlation_id=correlation_id,
            actor_id=actor_id,
            payload={
                "proposal_id": str(proposal.proposal_id),
                "search_profile_id": str(profile_id),
                "run_id": str(run.run_id) if run is not None else "",
            },
        )
        return updated

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _validate_reasons(
        self, event_type: str, reason_keys: tuple[str, ...]
    ) -> tuple[ReasonRef, ...]:
        seen: set[str] = set()
        refs: list[ReasonRef] = []
        for key in reason_keys:
            if key in seen:
                continue
            seen.add(key)
            reason = self.reasons.by_key().get(key)
            if reason is None:
                raise FeedbackInvalidReason(key)
            if not reason.allowed_for(event_type):  # type: ignore[arg-type]
                raise FeedbackInvalidReason(key)
            if reason.concept_key is not None and self.concepts.get(reason.concept_key) is None:
                raise FeedbackInvalidReason(key)
            refs.append(
                ReasonRef(
                    reason_key=reason.key,
                    polarity=reason.polarity,
                    concept_key=reason.concept_key,
                )
            )
        if len(refs) > 5:
            raise FeedbackValidationError(("feedback.too_many_reasons",))
        return tuple(refs)

    def _validate_free_feedback(self, free_feedback: str | None) -> str | None:
        if free_feedback is None:
            return None
        if not self.free_feedback_enabled:
            raise FeedbackValidationError(("feedback.free_feedback_disabled",))
        if len(free_feedback) > self.max_free_feedback_length:
            raise FeedbackValidationError(("feedback.free_feedback_too_long",))
        return free_feedback

    def _apply_shortlist(
        self,
        event_type: str,
        superseded: FeedbackEvent | None,
        profile_id: UUID,
        listing_id: UUID,
        now: datetime,
    ) -> None:
        if event_type == "save":
            self.shortlists.add(
                profile_id, listing_id, now, correlation_id=superseded.correlation_id if superseded else None
            )
        elif superseded is not None and superseded.event_type == "save":
            self.shortlists.remove(profile_id, listing_id)

    def _evaluate_learning(
        self,
        *,
        profile: SearchProfile,
        event: FeedbackEvent,
        correlation_id: UUID,
        actor_kind: str,
        actor_id: str | None,
    ) -> UUID | None:
        polarity = _EVENT_POLARITY.get(event.event_type)
        if polarity is None:
            return None
        policy = self.latest_learning_document()
        window_start = self.clock() - timedelta(days=policy.window_days)
        cooldown_start = self.clock() - timedelta(days=policy.cooldown_days)
        created: UUID | None = None
        for reason in event.reasons:
            if reason.concept_key is None:
                continue
            resolved = self.concepts.get(reason.concept_key)
            if resolved is None:
                continue
            concept_id, concept_key = resolved
            if self.proposals.pending_for_concept(profile.profile_id, concept_id) is not None:
                continue
            recent = self.proposals.recent_for_concept(
                profile.profile_id, concept_id, cooldown_start
            )
            if any(item.state in {"pending", "confirmed"} for item in recent):
                continue
            raw_signals = self.events.signal_events_since(
                profile.profile_id, concept_id, window_start
            )
            signals = tuple(
                Signal(
                    event_id=item.event_id,
                    concept_key=concept_key,
                    polarity=_EVENT_POLARITY.get(item.event_type, "negative"),
                    created_at=item.created_at,
                )
                for item in raw_signals
                if _EVENT_POLARITY.get(item.event_type) is not None
            )
            draft = evaluate_signals(
                policy=policy,
                concept_key=concept_key,
                polarity=polarity,
                signals=signals,
                now=self.clock(),
            )
            if draft is None:
                continue
            version = self.policies.latest_version(self.policy_seed_version)
            if version is None:
                continue
            expires_at = self.clock() + timedelta(days=policy.proposal_expiration_days)
            proposal = LearningProposal(
                proposal_id=uuid4(),
                profile_id=profile.profile_id,
                concept_id=concept_id,
                concept_key=concept_key,
                policy_version_id=version.version_id,
                policy_version=version.contract_version,
                change=ProposalChange(
                    kind="preference_fact",
                    concept_key=concept_key,
                    polarity=polarity,
                    suggested_weight=policy.default_suggested_weight,
                    suggested_confidence=policy.default_suggested_confidence,
                    value=None,
                ),
                prior_fact=None,
                evidence_refs=tuple(
                    {"feedback_event_id": str(event_id)}
                    for event_id in draft.evidence_event_ids
                ),
                state="pending",
                expires_at=expires_at,
                superseded_by=None,
                applied_profile_version_id=None,
                applied_run_id=None,
                created_at=self.clock(),
                correlation_id=correlation_id,
                actor_kind=actor_kind,
                actor_id=actor_id,
            )
            self.proposals.insert(proposal)
            created = proposal.proposal_id
            self._emit_server_event(
                event_type="learning.proposal_created.v1",
                correlation_id=correlation_id,
                actor_id=actor_id,
                payload={
                    "proposal_id": str(proposal.proposal_id),
                    "search_profile_id": str(profile.profile_id),
                    "concept_key": concept_key,
                    "polarity": polarity,
                    "evidence_count": len(draft.evidence_event_ids),
                    "policy_version": version.contract_version,
                },
            )
        return created

    def _expire_if_overdue(self, proposal: LearningProposal) -> LearningProposal:
        if proposal.state != "pending":
            return proposal
        if proposal.expires_at > self.clock():
            return proposal
        updated = self.proposals.update(_with_state(proposal, state="expired"))
        self._emit_server_event(
            event_type="learning.proposal_expired.v1",
            correlation_id=proposal.correlation_id,
            actor_id=proposal.actor_id,
            payload={
                "proposal_id": str(proposal.proposal_id),
                "search_profile_id": str(proposal.profile_id),
            },
        )
        return updated

    def _expire_overdue(self, proposals: tuple[LearningProposal, ...]) -> set[UUID]:
        expired: set[UUID] = set()
        for proposal in proposals:
            if proposal.state == "pending" and proposal.expires_at <= self.clock():
                self._expire_if_overdue(proposal)
                expired.add(proposal.proposal_id)
        return expired

    def _validate_change(self, change: ProposalChange) -> None:
        if change.kind != "preference_fact":
            raise FeedbackValidationError(("proposal.unsupported_kind",))
        if not change.concept_key or self.concepts.get(change.concept_key) is None:
            raise FeedbackValidationError(("proposal.unknown_concept",))
        if not is_polarity(change.polarity) or change.polarity == "neutral":
            raise FeedbackValidationError(("proposal.invalid_polarity",))
        if not 0.0 <= change.suggested_weight <= 1.0:
            raise FeedbackValidationError(("proposal.invalid_weight",))
        if not 0.0 <= change.suggested_confidence <= 1.0:
            raise FeedbackValidationError(("proposal.invalid_confidence",))

    def _active_fact(self, profile_id: UUID, concept_key: str) -> PreferenceFact | None:
        for fact in self.facts.active_for_profile(profile_id):
            if fact.concept_key == concept_key:
                return fact
        return None

    def _owned(self, owner_id: UUID, profile_id: UUID) -> SearchProfile:
        profile = self.profiles.get(profile_id)
        if profile is None or profile.owner_id != owner_id:
            raise FeedbackNotAccessible(f"profile not accessible: {profile_id}")
        return profile

    def _owned_proposal(self, profile_id: UUID, proposal_id: UUID) -> LearningProposal:
        proposal = self.proposals.get(proposal_id)
        if proposal is None or proposal.profile_id != profile_id:
            raise ProposalNotFound(f"proposal not found: {proposal_id}")
        return proposal

    def _emit_server_event(
        self,
        *,
        event_type: str,
        correlation_id: UUID,
        actor_id: str | None,
        payload: Mapping[str, object],
    ) -> None:
        version = event_version(self.events_registry, event_type)
        event = ProductEvent(
            event_id=uuid4(),
            event_type=event_type,
            event_version=version or 1,
            actor_id=(UUID(actor_id) if actor_id else None),
            occurred_at=self.clock(),
            correlation_id=correlation_id,
            payload=dict(payload),
        )
        self.events_out.insert(event)


def _as_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _with_state(
    proposal: LearningProposal,
    *,
    state: str,
    prior_fact: Mapping[str, object] | None = None,
    applied_profile_version_id: UUID | None = None,
    applied_run_id: UUID | None = None,
) -> LearningProposal:
    return LearningProposal(
        proposal_id=proposal.proposal_id,
        profile_id=proposal.profile_id,
        concept_id=proposal.concept_id,
        concept_key=proposal.concept_key,
        policy_version_id=proposal.policy_version_id,
        policy_version=proposal.policy_version,
        change=proposal.change,
        prior_fact=(
            dict(prior_fact)
            if prior_fact is not None
            else proposal.prior_fact
        ),
        evidence_refs=proposal.evidence_refs,
        state=state,  # type: ignore[arg-type]
        expires_at=proposal.expires_at,
        superseded_by=proposal.superseded_by,
        applied_profile_version_id=(
            applied_profile_version_id
            if applied_profile_version_id is not None
            else proposal.applied_profile_version_id
        ),
        applied_run_id=(
            applied_run_id if applied_run_id is not None else proposal.applied_run_id
        ),
        created_at=proposal.created_at,
        correlation_id=proposal.correlation_id,
        actor_kind=proposal.actor_kind,
        actor_id=proposal.actor_id,
    )


def _with_change(proposal: LearningProposal, change: ProposalChange) -> LearningProposal:
    return LearningProposal(
        proposal_id=proposal.proposal_id,
        profile_id=proposal.profile_id,
        concept_id=proposal.concept_id,
        concept_key=proposal.concept_key,
        policy_version_id=proposal.policy_version_id,
        policy_version=proposal.policy_version,
        change=change,
        prior_fact=proposal.prior_fact,
        evidence_refs=proposal.evidence_refs,
        state=proposal.state,
        expires_at=proposal.expires_at,
        superseded_by=proposal.superseded_by,
        applied_profile_version_id=proposal.applied_profile_version_id,
        applied_run_id=proposal.applied_run_id,
        created_at=proposal.created_at,
        correlation_id=proposal.correlation_id,
        actor_kind=proposal.actor_kind,
        actor_id=proposal.actor_id,
    )
