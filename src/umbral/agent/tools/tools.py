"""Tool implementations: thin, scoped delegations to application services (H4.2)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from umbral.agent.tools.contracts import ToolError, ToolRunContext
from umbral.agent.tools.executor import ToolImplementation
from umbral.application.agent.tools.contracts import ProposalError
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.criteria.contracts import Compilation
from umbral.application.feedback.contracts import FeedbackRecord
from umbral.application.radar.contracts import (
    ListingDetail,
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


def build_tool_implementations(services: ToolServices) -> dict[str, ToolImplementation]:
    return {
        "get_search_profile": _get_search_profile(services),
        "propose_search_profile_update": _propose(services),
        "apply_search_profile_update": _apply(services),
        "find_matches": _find_matches(services),
        "explain_match": _explain_match(services),
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


def _record_feedback(services: ToolServices) -> ToolImplementation:
    def run(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        listing_id = UUID(str(args["listing_id"]))
        decision = str(args["decision"])
        if decision not in {"like", "dislike"}:
            raise ToolError(code="tool.args_invalid")
        services.radar.get_listing_detail(
            owner_id=context.user_id, listing_id=listing_id
        )
        run_obj = services.radar.latest_run_of(
            services.radar.get_profile(
                owner_id=context.user_id, profile_id=context.search_profile_id
            )
        )
        raw_reasons = args.get("reason_keys")
        reason_keys = (
            tuple(str(item) for item in raw_reasons)
            if isinstance(raw_reasons, list)
            else ()
        )
        record = services.feedback.record_feedback(
            owner_id=context.user_id,
            profile_id=context.search_profile_id,
            listing_id=listing_id,
            run_id=run_obj.run_id if run_obj is not None else None,
            event_type=decision,
            reason_keys=reason_keys,
            idempotency_key=str(args["idempotency_key"]),
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


