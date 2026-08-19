"""Tool implementations: thin, scoped delegations to application services (H4.2)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from umbral.agent.tools.contracts import ToolError, ToolRunContext
from umbral.agent.tools.executor import ToolImplementation
from umbral.application.agent.tools.contracts import ProposalError
from umbral.application.agent.tools.preferences import (
    PreferenceIntent,
    PreferenceVocabularyError,
    PreferenceVocabularySpec,
)
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.criteria.contracts import Compilation, PreferenceFact
from umbral.application.feedback.contracts import (
    FeedbackRecord,
    FeedbackValidationError,
    LearningProposal,
    PreferenceImpact,
)
from umbral.application.radar.contracts import (
    ListingDetail,
    ListingNotAccessible,
    MatchPage,
    RecommendationRun,
    RunNotFound,
    SearchProfile,
)
from umbral.application.scoring.contracts import Comparison, Explanation


class RadarPort(Protocol):
    def get_profile(self, *, owner_id: UUID, profile_id: UUID) -> SearchProfile: ...

    def get_matches(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        run_id: UUID | None,
        after_position: int | None,
        limit: int,
        include_dismissed: bool = False,
    ) -> MatchPage: ...

    def latest_run_of(self, profile: SearchProfile) -> RecommendationRun | None: ...

    def get_listing_detail(self, owner_id: UUID, listing_id: UUID) -> ListingDetail: ...

    def validate_change(
        self, *, owner_id: UUID, profile_id: UUID, changes: Mapping[str, object]
    ) -> SearchProfile: ...

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
    ) -> tuple[SearchProfile, object | None]: ...


class ScoringPort(Protocol):
    def get_explanation(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        run_id: UUID,
        listing_id: UUID,
    ) -> Explanation: ...

    def build_comparison(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        listing_ids: tuple[UUID, ...],
    ) -> Comparison: ...


class FeedbackPort(Protocol):
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
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> FeedbackRecord: ...

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
    ) -> tuple[LearningProposal, PreferenceImpact]: ...

    def active_preferences(
        self, *, owner_id: UUID, profile_id: UUID
    ) -> tuple[PreferenceFact, ...]: ...

    def get_proposal(
        self, *, owner_id: UUID, profile_id: UUID, proposal_id: UUID
    ) -> LearningProposal: ...

    def propose_preference_removal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        concept_key: str,
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> tuple[LearningProposal, PreferenceImpact]: ...


class CriteriaPort(Protocol):
    def latest_compilation(
        self, profile_version_id: UUID
    ) -> Compilation | None: ...

    def list_urban_signals(
        self, listing_id: UUID
    ) -> tuple[Mapping[str, object], ...]: ...


@dataclass(frozen=True, slots=True)
class ToolServices:
    """Application services a tool may delegate to; never infrastructure."""

    radar: RadarPort
    scoring: ScoringPort
    feedback: FeedbackPort
    criteria: CriteriaPort
    proposals: SearchProfileUpdateProposals
    vocabulary: PreferenceVocabularySpec
    preferences: object | None = None
    interpret_preference: object | None = None


def build_tool_implementations(services: ToolServices) -> dict[str, ToolImplementation]:
    return {
        "get_search_profile": _get_search_profile(services),
        "propose_search_profile_update": _propose(services),
        "propose_search_preference_update": _propose_preference(services),
        "propose_search_preference_removal": _propose_preference_removal(services),
        "propose_learning_confirmation": _propose_learning_confirmation(services),
        "apply_search_profile_update": _apply(services),
        "find_matches": _find_matches(services),
        "explain_match": _explain_match(services),
        "get_listing_detail": _get_listing_detail(services),
        "list_search_preferences": _list_preferences(services),
        "compare_listings": _compare_listings(services),
        "record_feedback": _record_feedback(services),
        "search_urban_context": _search_urban_context(services),
    }


def _get_search_profile(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, _args: Mapping[str, object]
    ) -> Mapping[str, object]:
        profile = services.radar.get_profile(
            owner_id=context.user_id, profile_id=context.search_profile_id
        )
        criteria: list[Mapping[str, object]] = []
        if profile.current_version_id is not None:
            compilation = services.criteria.latest_compilation(
                profile.current_version_id
            )
            if compilation is not None:
                criteria = [
                    {
                        "concept_key": item.concept_key,
                        "matcher_type": item.matcher_type,
                        "params": dict(item.params),
                        "soft_to_hard": item.soft_to_hard,
                    }
                    for item in compilation.criteria
                ]
        return {
            "profile_id": str(profile.profile_id),
            "state": profile.status,
            "snapshot": {
                "name": profile.name,
                "operation": profile.operation,
                "zones": list(profile.zones),
                "budget_max": profile.budget_max,
                "budget_min": profile.budget_min,
                "min_rooms": profile.min_rooms,
                "surface_min": profile.surface_min,
                "surface_max": profile.surface_max,
                "version": profile.version,
            },
            "criteria": criteria,
        }

    return run


def _propose(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        try:
            change = args.get("change")
            if not isinstance(change, Mapping):
                raise ToolError(code="tool.args_invalid")
            proposal = services.proposals.propose(
                user_id=context.user_id,
                session_id=context.session_id,
                search_profile_id=context.search_profile_id,
                change=dict(change),
                correlation_id=context.correlation_id,
            )
        except ProposalError as error:
            raise _tool_error(error) from error
        return {
            "proposal_id": str(proposal.proposal_id),
            "diff": proposal.diff,
            "impact": proposal.impact,
            "state": proposal.state,
            "expires_at": proposal.expires_at.isoformat(),
        }

    return run


def _propose_preference(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        phrase = args.get("preference")
        if not isinstance(phrase, str) or not phrase.strip():
            raise ToolError(code="tool.args_invalid")
        if services.preferences is not None:
            return _propose_preference_llm(services, context, phrase)
        try:
            intent: PreferenceIntent = services.vocabulary.resolve(phrase)
        except PreferenceVocabularyError as error:
            raise ToolError(code=error.code) from error
        if intent.requires_value and intent.value is None:
            raise ToolError(code="preference.value_required")
        try:
            proposal, impact = services.feedback.propose_preference(
                owner_id=context.user_id,
                profile_id=context.search_profile_id,
                concept_key=intent.concept_key,
                polarity=intent.polarity,
                value=intent.value,
                correlation_id=context.correlation_id,
                actor_kind="user",
                actor_id=str(context.user_id),
            )
        except FeedbackValidationError as error:
            code = error.error_codes[0] if error.error_codes else "preference.error"
            raise ToolError(code=code) from error
        diff: dict[str, object] = {
            "concept_key": proposal.change.concept_key,
            "polarity": proposal.change.polarity,
        }
        if proposal.change.value is not None:
            diff["concept_value"] = proposal.change.value
        return {
            "proposal_id": str(proposal.proposal_id),
            "diff": diff,
            "impact": {
                "concept_key": proposal.change.concept_key,
                "polarity": proposal.change.polarity,
                "will_recompute": True,
                "contradicts": bool(impact.contradicts),
                "current_fact": dict(impact.current) if impact.current else None,
            },
            "state": proposal.state,
            "expires_at": proposal.expires_at.isoformat(),
        }

    return run


def _propose_preference_llm(
    services: ToolServices, context: ToolRunContext, phrase: str
) -> Mapping[str, object]:
    """Interpret the phrase with the LLM, persist the durable expression and
    binding, and only surface a computable preference when a canonical concept
    was resolved (unresolved phrases are preserved, never rejected).
    """
    from umbral.application.preferences.contracts import (
        BindingDraft,
        PreferenceError,
    )

    interpretation = _interpret_phrase(services, phrase)
    if interpretation is None or interpretation.kind != "structured":
        reason = (
            getattr(interpretation, "reason", None)
            if interpretation is not None
            else "interpretation_failed"
        )
        _record_expression(
            services,
            context,
            phrase,
            binding_drafts=(BindingDraft.unresolved(str(reason)),),
        )
        return {
            "outcome": "preserved",
            "preserved": True,
            "kind": "unresolved",
            "reason": str(reason),
            "expires_at": None,
            "proposal_id": None,
        }

    concept_key = interpretation.concept_key
    assert concept_key is not None
    binding = BindingDraft.structured(
        concept_key=concept_key,
        matcher_type=interpretation.matcher_type or "signal_score",
        params=dict(interpretation.params),
        confidence=interpretation.confidence,
        evidence_refs=({"pipeline": "agent.preference_interpreter", "version": "v1"},),
        limitations=(),
    )
    try:
        _record_expression(
            services,
            context,
            phrase,
            binding_drafts=(binding,),
        )
    except PreferenceError as error:
        # The phrase resolved to a canonical concept, but persisting the
        # structured binding was rejected by deterministic policy or registry
        # state (e.g. unseeded concept). Preserve the phrase as unresolved
        # instead of surfacing an opaque technical error to the user.
        reason = str(error)
        _record_expression(
            services,
            context,
            phrase,
            binding_drafts=(BindingDraft.unresolved(reason),),
        )
        return {
            "outcome": "preserved",
            "preserved": True,
            "kind": "unresolved",
            "reason": reason,
            "expires_at": None,
            "proposal_id": None,
        }
    return {
        "outcome": "proposed",
        "preserved": False,
        "kind": "structured",
        "concept_key": interpretation.concept_key,
        "polarity": interpretation.polarity,
        "value": interpretation.value,
        "confidence": interpretation.confidence,
        "matcher_type": binding.matcher_type,
        "proposal_id": None,
        "expires_at": None,
    }


def _interpret_phrase(services: ToolServices, phrase: str) -> Any:
    """Run the LLM interpreter, or a raw phrase with a safe default on failure.

    Interpreter failures (gateway, network, unexpected provider output) never
    raise into the tool: the phrase is preserved as unresolved (FR-010), never
    surfaced as a generic technical error.
    """
    interpret = services.interpret_preference
    if not callable(interpret):
        return None
    try:
        return interpret(phrase)
    except Exception:  # noqa: BLE001 - interpreter failure preserves the phrase
        return None


def _record_expression(
    services: ToolServices,
    context: ToolRunContext,
    raw_text: str,
    *,
    binding_drafts: tuple[object, ...],
) -> None:
    preferences = getattr(services.preferences, "record_expression", None)
    if preferences is None:
        raise ToolError(code="preference.interpreter_unavailable")
    preferences(
        profile_id=context.search_profile_id,
        source_message_id=None,
        subject_key=_subject_key(raw_text),
        raw_text=raw_text,
        authority="explicit",
        binding_drafts=binding_drafts,
        correlation_id=context.correlation_id,
    )


def _subject_key(raw_text: str) -> str:
    from umbral.application.agent.tools.preferences import _alias_key

    return _alias_key(raw_text) or raw_text.strip().casefold() or "preferencia"


def _propose_preference_removal(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        phrase = args.get("preference")
        if not isinstance(phrase, str) or not phrase.strip():
            raise ToolError(code="tool.args_invalid")
        try:
            intent: PreferenceIntent = services.vocabulary.resolve(phrase)
        except PreferenceVocabularyError as error:
            raise ToolError(code=error.code) from error
        try:
            proposal, impact = services.feedback.propose_preference_removal(
                owner_id=context.user_id,
                profile_id=context.search_profile_id,
                concept_key=intent.concept_key,
                correlation_id=context.correlation_id,
                actor_kind="user",
                actor_id=str(context.user_id),
            )
        except FeedbackValidationError as error:
            code = error.error_codes[0] if error.error_codes else "preference.error"
            raise ToolError(code=code) from error
        diff: dict[str, object] = {
            "concept_key": proposal.change.concept_key,
            "polarity": proposal.change.polarity,
            "operation": "remove",
        }
        return {
            "proposal_id": str(proposal.proposal_id),
            "diff": diff,
            "impact": {
                "concept_key": proposal.change.concept_key,
                "polarity": proposal.change.polarity,
                "will_recompute": True,
                "operation": "remove",
                "current_fact": dict(impact.current) if impact.current else None,
            },
            "state": proposal.state,
            "expires_at": proposal.expires_at.isoformat(),
        }

    return run


def _propose_learning_confirmation(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        try:
            proposal = services.feedback.get_proposal(
                owner_id=context.user_id,
                profile_id=context.search_profile_id,
                proposal_id=UUID(str(args["learning_proposal_id"])),
            )
        except Exception as exc:  # noqa: BLE001 - sanitized at the boundary
            if type(exc).__name__ in {"ProposalNotFound", "FeedbackNotFound"}:
                raise ToolError(code="preference.not_found") from exc
            raise
        if proposal.state != "pending":
            raise ToolError(code="preference.not_pending")
        diff: dict[str, object] = {
            "concept_key": proposal.change.concept_key,
            "polarity": proposal.change.polarity,
            "operation": "learning",
        }
        return {
            "proposal_id": str(proposal.proposal_id),
            "diff": diff,
            "impact": {
                "concept_key": proposal.change.concept_key,
                "polarity": proposal.change.polarity,
                "will_recompute": True,
                "operation": "learning",
                "source": "feedback",
            },
            "state": proposal.state,
            "expires_at": proposal.expires_at.isoformat(),
        }

    return run


def _list_preferences(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, _args: Mapping[str, object]
    ) -> Mapping[str, object]:
        facts = services.feedback.active_preferences(
            owner_id=context.user_id, profile_id=context.search_profile_id
        )
        return {
            "preferences": [
                {
                    "concept_key": fact.concept_key,
                    "polarity": fact.polarity,
                    "fact_source": fact.fact_source,
                    "created_at": fact.created_at.isoformat(),
                }
                for fact in facts
            ]
        }

    return run


def _apply(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        try:
            result = services.proposals.apply(
                user_id=context.user_id,
                session_id=context.session_id,
                search_profile_id=context.search_profile_id,
                proposal_id=UUID(str(args["proposal_id"])),
                confirmation=bool(args["confirmation"]),
                idempotency_key=str(args["idempotency_key"]),
                correlation_id=context.correlation_id,
            )
        except ProposalError as error:
            raise _tool_error(error) from error
        return {
            "proposal_id": str(result.proposal_id),
            "state": result.state,
            "profile_version": result.profile_version,
            "run_id": str(result.run_id) if result.run_id else None,
        }

    return run


def _find_matches(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        limit = _bounded_int(args.get("limit"), 20)
        try:
            page = services.radar.get_matches(
                owner_id=context.user_id,
                profile_id=context.search_profile_id,
                run_id=None,
                after_position=None,
                limit=limit,
            )
        except RunNotFound:
            return {"run_id": None, "items": [], "total": 0, "stale": True}
        run_obj = page.run
        if run_obj is None:
            return {"run_id": None, "items": [], "total": 0, "stale": True}
        stale = run_obj.state != "succeeded"
        items = [
            {
                "item_id": str(item.item_id),
                "listing_id": str(item.listing_id),
                "score": item.score,
                "position": item.position,
            }
            for item in page.items
        ]
        return {
            "run_id": str(run_obj.run_id),
            "items": items,
            "total": len(items),
            "stale": stale,
        }

    return run


def _explain_match(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        listing_id = UUID(str(args["listing_id"]))
        profile = services.radar.get_profile(
            owner_id=context.user_id, profile_id=context.search_profile_id
        )
        run_obj = services.radar.latest_run_of(profile)
        if run_obj is None or run_obj.state != "succeeded":
            raise ToolError(code="tool.no_run")
        explanation = services.scoring.get_explanation(
            owner_id=context.user_id,
            profile_id=context.search_profile_id,
            run_id=run_obj.run_id,
            listing_id=listing_id,
        )
        return {
            "listing_id": str(listing_id),
            "score_version": explanation.score_version,
            "reasons": [
                {
                    "criterion_key": reason.criterion_key,
                    "evidence_level": reason.evidence_level,
                    "text": reason.text,
                }
                for reason in explanation.reasons
            ],
            "risks": [risk.text for risk in explanation.risks],
            "missing_data": list(explanation.missing_data),
            "evidence_refs": _flatten_evidence_refs(explanation.reasons),
        }

    return run


def _get_listing_detail(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        listing_id = UUID(str(args["listing_id"]))
        detail = _accessible_detail(services, context, listing_id)
        return {
            "listing_id": str(detail.listing_id),
            "source_id": detail.source_id,
            "neighborhood": detail.neighborhood,
            "geo_precision": detail.geo_precision,
            "total_cost": detail.total_cost,
            "price_value": detail.price_value,
            "price_currency": detail.price_currency,
            "expenses_value": detail.expenses_value,
            "surface_m2": detail.surface_m2,
            "rooms": detail.rooms,
            "bedrooms": detail.bedrooms,
            "floor": detail.floor,
            "property_type": detail.property_type,
            "amenities": list(detail.amenities),
            "known_changes": [dict(item) for item in detail.known_changes],
        }

    return run


def _compare_listings(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        raw_ids = args.get("listing_ids")
        if not isinstance(raw_ids, list):
            raise ToolError(code="tool.args_invalid")
        listing_ids = tuple(UUID(str(item)) for item in raw_ids)
        comparison = services.scoring.build_comparison(
            owner_id=context.user_id,
            profile_id=context.search_profile_id,
            listing_ids=listing_ids,
        )
        return {
            "comparison": _comparison_payload(comparison),
            "dimensions": [dim.key for dim in comparison.dimensions],
            "missing": _comparison_missing(comparison),
        }

    return run


_REASON_LABEL_KEYS = {
    "poca luz": "lighting_bad",
    "sin luz": "lighting_bad",
    "precio alto": "price_too_high",
    "precio": "price_too_high",
    "caro": "price_too_high",
    "expensas altas": "expensas_high",
    "expensas": "expensas_high",
    "ubicacion": "location_no",
    "ubicacion no": "location_no",
    "ambientes": "rooms_wrong",
    "superficie chica": "surface_wrong",
    "superficie": "surface_wrong",
    "estado del edificio": "building_state",
    "estado": "building_state",
    "otra razon": "other",
    "otro": "other",
}


def _normalize_reason_keys(raw_reasons: object) -> tuple[str, ...]:
    """Map natural reason labels to canonical quick-reason keys (0 LLM)."""
    if not isinstance(raw_reasons, list):
        return ()
    keys: list[str] = []
    for item in raw_reasons:
        if not isinstance(item, str):
            continue
        key = item.strip().lower()
        if key in _REASON_LABEL_KEYS:
            key = _REASON_LABEL_KEYS[key]
        if key not in keys:
            keys.append(key)
    return tuple(keys)


def _record_feedback(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        listing_id = UUID(str(args["listing_id"]))
        decision = str(args["decision"])
        if decision not in {"like", "dislike"}:
            raise ToolError(code="tool.args_invalid")
        _accessible_detail(services, context, listing_id)
        run_obj = services.radar.latest_run_of(
            services.radar.get_profile(
                owner_id=context.user_id, profile_id=context.search_profile_id
            )
        )
        reason_keys = _normalize_reason_keys(args.get("reason_keys"))
        record = services.feedback.record_feedback(
            owner_id=context.user_id,
            profile_id=context.search_profile_id,
            listing_id=listing_id,
            run_id=run_obj.run_id if run_obj is not None else None,
            event_type=decision,
            reason_keys=reason_keys,
            idempotency_key=str(args.get("idempotency_key", "")),
            correlation_id=context.correlation_id,
            actor_kind="user",
            actor_id=str(context.user_id),
        )
        return {
            "event_id": str(record.event.event_id),
            "noop": record.noop,
            "learning_proposal_id": (
                str(record.learning_proposal_id)
                if record.learning_proposal_id is not None
                else None
            ),
        }

    return run


def _search_urban_context(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        listing_id = UUID(str(args["listing_id"]))
        detail = services.radar.get_listing_detail(
            owner_id=context.user_id, listing_id=listing_id
        )
        raw_types = args.get("signal_types")
        wanted = set(raw_types) if isinstance(raw_types, list) else None
        signals = services.criteria.list_urban_signals(listing_id)
        filtered = [dict(signal) for signal in signals]
        if wanted:
            filtered = [
                signal for signal in filtered if signal.get("signal_type") in wanted
            ]
        return {
            "signals": filtered,
            "precision": detail.geo_precision,
        }

    return run


def _tool_error(error: ProposalError) -> ToolError:
    return ToolError(code=error.code)


def _accessible_detail(
    services: ToolServices, context: ToolRunContext, listing_id: UUID
) -> ListingDetail:
    try:
        return services.radar.get_listing_detail(
            owner_id=context.user_id, listing_id=listing_id
        )
    except ListingNotAccessible as exc:
        raise ToolError(code="tool.listing_not_accessible") from exc


def _bounded_int(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return max(1, min(value, 20))
    return default


def _flatten_evidence_refs(reasons: Sequence[object]) -> list[Mapping[str, object]]:
    refs: list[Mapping[str, object]] = []
    for reason in reasons:
        for ref in getattr(reason, "evidence_refs", ()):
            if isinstance(ref, Mapping):
                refs.append(dict(ref))
    return refs


def _comparison_payload(comparison: Comparison) -> Mapping[str, object]:
    return {
        "cells": [
            {
                "listing_id": str(cell.listing_id),
                "dimension": cell.dimension_key,
                "value": _jsonable(cell.value),
                "state": cell.state,
                "missing": cell.missing,
            }
            for cell in comparison.cells
        ]
    }


def _comparison_missing(comparison: Comparison) -> list[Mapping[str, object]]:
    return [
        {
            "dimension": cell.dimension_key,
            "listing_id": str(cell.listing_id),
            "state": cell.state,
        }
        for cell in comparison.cells
        if cell.missing
    ]


def _jsonable(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return str(value)


