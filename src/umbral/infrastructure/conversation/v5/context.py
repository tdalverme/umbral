"""Authorized V5 context assembly over explicit application services.

The assembler resolves the chat session, its bound radar and version, active
preference expressions as desire refs, the durable pending proposal, and the
focus-reader-verified listing. Read failures become typed ``context_failure``
reason codes; an ownership failure is never degraded into an unbound context.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from umbral.application.agent.tools.proposals import (
    SearchProfileUpdateProposals,
)
from umbral.application.chat.contracts import ChatSession, ChatSessionNotFound
from umbral.application.chat.service import ChatService
from umbral.application.conversation.v5.contracts import (
    ConceptLinkV5,
    DesireViewV5,
    FocusedEntityV5,
    HardFilterV5,
    PendingActionV5,
    TurnContextV5,
    UntrustedContentV5,
)
from umbral.application.conversation.v5.ports import (
    ContextAssemblyFailed,
    FocusedEntityReader,
    PendingActionReaderV5,
)
from umbral.application.preferences.contracts import PreferenceView
from umbral.application.radar.contracts import (
    RadarError,
    RadarNotAccessible,
    SearchProfile,
)
from umbral.application.radar.service import RadarService
from umbral.infrastructure.conversation.composition import PreferenceServiceLike

Clock = Callable[[], datetime]

_ALL_ACT_KINDS = (
    "create_radar",
    "set_filter",
    "clear_filter",
    "express_desire",
    "revise_desire",
    "withdraw_desire",
    "record_feedback",
    "resolve_pending",
    "query",
    "unsupported_request",
)


class ContextAssemblerV5:
    """Builds the least-authority V5 turn context from explicit services."""

    def __init__(
        self,
        *,
        chat: ChatService,
        radar: RadarService,
        preferences: PreferenceServiceLike | None,
        pending: PendingActionReaderV5,
        focus: FocusedEntityReader,
        allowed_capabilities: tuple[str, ...] = _ALL_ACT_KINDS,
        clock: Clock | None = None,
    ) -> None:
        self.chat = chat
        self.radar = radar
        self.preferences = preferences
        self.pending = pending
        self.focus = focus
        self.allowed_capabilities = allowed_capabilities
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def load(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        correlation_id: UUID,
    ) -> TurnContextV5:
        session = self._session(user_id=user_id, session_id=session_id)
        profile_id = session.search_profile_id
        radar_ref, radar_version, filters = self._radar_view(
            user_id=user_id, profile_id=profile_id
        )
        desires = self._desire_views(profile_id=profile_id)
        pending = self.pending.active_for_session(
            user_id=user_id, session_id=session_id, profile_id=profile_id
        )
        listing = self.focus.verified_focus(user_id=user_id, session_id=session_id)
        return TurnContextV5(
            user_id=str(user_id),
            session_id=str(session_id),
            active_radar_ref=radar_ref,
            active_radar_version=radar_version,
            current_filters=filters,
            active_desires=desires,
            pending_action=pending,
            focused_entity=(
                FocusedEntityV5(entity_ref=listing.entity_ref)
                if listing is not None
                else None
            ),
            verified_listing_refs=(listing.entity_ref,) if listing is not None else (),
            allowed_capabilities=self.allowed_capabilities,
            untrusted_content=(
                (
                    UntrustedContentV5(
                        source="listing", text=listing.text, may_supply_evidence=False
                    ),
                )
                if listing is not None
                else ()
            ),
            context_schema_version="5",
            correlation_id=str(correlation_id),
        )

    def _session(self, *, user_id: UUID, session_id: UUID) -> ChatSession:
        try:
            return self.chat.get_session(user_id=user_id, session_id=session_id)
        except ChatSessionNotFound as error:
            raise ContextAssemblyFailed("context.session_not_found") from error

    def _radar_view(
        self, *, user_id: UUID, profile_id: UUID | None
    ) -> tuple[str | None, int | None, tuple[HardFilterV5, ...]]:
        if profile_id is None:
            return None, None, ()
        try:
            profile = self.radar.get_profile(owner_id=user_id, profile_id=profile_id)
        except RadarNotAccessible as error:
            raise ContextAssemblyFailed("context.ownership_rejected") from error
        except RadarError as error:
            raise ContextAssemblyFailed("context.radar_unreadable") from error
        return (
            f"radar:{profile.profile_id}",
            profile.version,
            _filters_from_profile(profile),
        )

    def _desire_views(self, *, profile_id: UUID | None) -> tuple[DesireViewV5, ...]:
        if self.preferences is None or profile_id is None:
            return ()
        try:
            views = self.preferences.active_view(profile_id)
        except Exception as error:  # noqa: BLE001 - preference store unreadable
            raise ContextAssemblyFailed("context.preferences_unreadable") from error
        return tuple(_desire_view(view) for view in views)


class ProposalsPendingReaderV5:
    """Adapts the durable proposal store to the V5 pending-action port."""

    def __init__(self, *, proposals: SearchProfileUpdateProposals) -> None:
        self.proposals = proposals

    def active_for_session(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        profile_id: UUID | None,
    ) -> PendingActionV5 | None:
        if profile_id is None:
            return None
        repository = getattr(self.proposals, "repository", None)
        latest = getattr(repository, "latest_pending_for_profile", None)
        if latest is None:
            return None
        try:
            proposal = latest(profile_id, session_id)
        except Exception:  # noqa: BLE001 - pending store unreadable
            return None
        if proposal is None:
            return None
        return PendingActionV5(pending_ref=f"pending:{proposal.proposal_id}")


def _filters_from_profile(profile: SearchProfile) -> tuple[HardFilterV5, ...]:
    filters: list[HardFilterV5] = []
    if profile.zones:
        filters.append(HardFilterV5(filter_key="zones", value=tuple(profile.zones)))
    if profile.budget_max is not None:
        filters.append(HardFilterV5(filter_key="budget_max", value=profile.budget_max))
    if profile.min_rooms is not None:
        filters.append(HardFilterV5(filter_key="min_rooms", value=profile.min_rooms))
    return tuple(filters)


def _desire_view(view: PreferenceView) -> DesireViewV5:
    concept_links: tuple[ConceptLinkV5, ...] = ()
    if (
        view.binding_id is not None
        and view.mode == "soft"
        and view.binding_kind in ("structured", "semantic")
    ):
        concept_links = (
            ConceptLinkV5(
                concept_ref=f"binding:{view.binding_id}",
                confidence=view.confidence,
                polarity="positive",
                intensity="medium",
                evidence_spans=(),
                force="soft",
            ),
        )
    return DesireViewV5(
        desire_ref=f"desire:{view.expression_id}",
        raw_text=view.raw_text,
        subject_ref=view.subject_key,
        concept_links=concept_links,
    )
