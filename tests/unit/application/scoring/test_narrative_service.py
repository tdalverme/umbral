"""Service coverage for selected-opportunity narratives."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from tests.support.radar import build_listing, build_profile, profile_version_payload
from tests.support.scoring import (
    ScoringTestContext,
    build_compilation,
    build_criterion,
    build_item,
    build_run,
)

from umbral.application.radar.contracts import ProfileVersion
from umbral.application.scoring.contracts import (
    CriterionEvaluation,
    ExplanationNarrativeContext,
)
from umbral.application.scoring.narrative import ExplanationNarrative


class RecordingNarrativeWriter:
    def __init__(self) -> None:
        self.contexts: list[ExplanationNarrativeContext] = []

    def write(self, context: ExplanationNarrativeContext) -> ExplanationNarrative:
        self.contexts.append(context)
        return ExplanationNarrative(
            text="Encaja por la luz natural.",
            used_criteria=("luminosidad",),
            used_evidence_refs=("listing_field:total_cost",),
            source="deterministic_fallback",
            prompt_version="test",
            model_version="test",
        )


class RecordingNarrativeCache:
    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, UUID, str, str, str], ExplanationNarrative] = {}
        self.puts = 0

    def get(
        self,
        *,
        run_id: UUID,
        listing_id: UUID,
        prompt_version: str,
        model_version: str,
        schema_version: str,
    ) -> ExplanationNarrative | None:
        return self.rows.get(
            (run_id, listing_id, prompt_version, model_version, schema_version)
        )

    def put(
        self,
        *,
        run_id: UUID,
        listing_id: UUID,
        prompt_version: str,
        model_version: str,
        schema_version: str,
        narrative: ExplanationNarrative,
        now: datetime,
        correlation_id: UUID,
    ) -> None:
        del now, correlation_id
        self.puts += 1
        self.rows[
            (run_id, listing_id, prompt_version, model_version, schema_version)
        ] = narrative


def _context() -> tuple[
    ScoringTestContext, RecordingNarrativeWriter, UUID, UUID, UUID, UUID
]:
    context = ScoringTestContext()
    writer = RecordingNarrativeWriter()
    context.service.narrative_writer = writer
    owner_id, profile_id, run_id, listing_id, profile_version_id = (
        uuid4() for _ in range(5)
    )
    score_policy_version = context.service.pin_policy_version()
    profile = build_profile(owner_id=owner_id, profile_id=profile_id)
    context.profiles.rows[profile_id] = profile
    context.versions.rows[profile_version_id] = ProfileVersion(
        version_id=profile_version_id,
        profile_id=profile_id,
        profile_version=1,
        payload=profile_version_payload(profile),
        created_at=profile.created_at,
        correlation_id=profile.correlation_id,
    )
    context.runs.rows[run_id] = build_run(
        profile_id=profile_id,
        profile_version_id=profile_version_id,
        run_id=run_id,
        score_policy_version=score_policy_version,
    )
    context.items.items_by_run[run_id] = [
        replace(
            build_item(run_id, listing_id),
            contributions={
                "_narrative_listing": {
                    "listing_id": str(listing_id),
                    "price_value": 700.0,
                    "price_currency": "ARS",
                    "price_changes": (),
                },
                "_narrative_observations": {},
            },
        )
    ]
    context.listings.rows[listing_id] = build_listing(listing_id=listing_id)
    context.compilations.compilations[profile_version_id] = build_compilation(
        profile_id=profile_id,
        profile_version_id=profile_version_id,
        criteria=(build_criterion("luminosidad"),),
    )
    context.evaluations.rows.extend(
        (
            _evaluation(run_id, listing_id, score_policy_version, "luminosidad"),
            _evaluation(run_id, listing_id, score_policy_version, "balcon"),
        )
    )
    return context, writer, owner_id, profile_id, run_id, listing_id


def _evaluation(
    run_id: UUID, listing_id: UUID, score_policy_version: str, criterion_key: str
) -> CriterionEvaluation:
    return CriterionEvaluation(
        evaluation_id=uuid4(), run_id=run_id, listing_id=listing_id,
        criterion_key=criterion_key, criterion_version=f"policy:{score_policy_version}",
        matcher_type="categorical", params={}, input_refs=(), score=1.0,
        confidence=1.0, state="match", contribution=0.1,
        reason_code="concept_observed",
        evidence_refs=({"kind": "listing_field", "ref": "total_cost"},),
        created_at=datetime.now(timezone.utc), correlation_id=uuid4(),
    )


def test_narrative_uses_frozen_run_profile_and_listing_context() -> None:
    context, writer, owner_id, profile_id, run_id, listing_id = _context()

    result = context.service.get_narrative(
        owner_id=owner_id, profile_id=profile_id, run_id=run_id, listing_id=listing_id
    )

    assert result.text
    assert writer.contexts[-1].run_id == run_id
    assert "balcon" not in {
        item["key"] for item in writer.contexts[-1].active_priorities
    }
    assert writer.contexts[-1].listing["price"] == 700.0


def test_narrative_reuses_persisted_result_for_same_run_and_versions() -> None:
    context, writer, owner_id, profile_id, run_id, listing_id = _context()
    cache = RecordingNarrativeCache()
    context.service.narrative_cache = cache

    first = context.service.get_narrative(
        owner_id=owner_id, profile_id=profile_id, run_id=run_id, listing_id=listing_id
    )
    second = context.service.get_narrative(
        owner_id=owner_id, profile_id=profile_id, run_id=run_id, listing_id=listing_id
    )

    assert second == first
    assert len(writer.contexts) == 1
    assert cache.puts == 1


def test_narrative_cache_misses_when_model_version_changes() -> None:
    context, writer, owner_id, profile_id, run_id, listing_id = _context()
    cache = RecordingNarrativeCache()
    context.service.narrative_cache = cache

    context.service.get_narrative(
        owner_id=owner_id, profile_id=profile_id, run_id=run_id, listing_id=listing_id
    )
    context.service.narrative_model_version = "model-v2"
    context.service.get_narrative(
        owner_id=owner_id, profile_id=profile_id, run_id=run_id, listing_id=listing_id
    )

    assert len(writer.contexts) == 2
    assert cache.puts == 2


def test_list_explanations_does_not_call_narrative_writer() -> None:
    context, writer, owner_id, profile_id, run_id, _ = _context()

    context.service.list_explanations(
        owner_id=owner_id, profile_id=profile_id, run_id=run_id,
        after_position=None, limit=25,
    )

    assert writer.contexts == []


def test_narrative_ignores_frozen_observation_for_another_listing() -> None:
    context, writer, owner_id, profile_id, run_id, listing_id = _context()
    other_listing_id = uuid4()
    item = context.items.items_by_run[run_id][0]
    context.items.items_by_run[run_id][0] = replace(
        item,
        contributions={
            **item.contributions,
            "_narrative_observations": {
                "luminosidad": {
                    "observation_id": str(uuid4()),
                    "listing_id": str(other_listing_id),
                    "concept_key": "luminosidad",
                    "matcher_type": "signal_score",
                    "value": 0.8,
                    "score": 0.8,
                    "confidence": 0.8,
                    "evidence": {
                        "signal_ref": "transit_access",
                        "contributors": [
                            {
                                "term": "subway_station.nearest_m",
                                "observed_value": 300,
                                "unit": "m",
                            }
                        ],
                    },
                    "source": "urban",
                    "state": "active",
                }
            },
        },
    )

    context.service.get_narrative(
        owner_id=owner_id, profile_id=profile_id, run_id=run_id, listing_id=listing_id
    )

    assert writer.contexts[-1].geography == ()


def test_narrative_ignores_frozen_listing_for_another_listing() -> None:
    context, writer, owner_id, profile_id, run_id, listing_id = _context()
    item = context.items.items_by_run[run_id][0]
    context.items.items_by_run[run_id][0] = replace(
        item,
        contributions={
            **item.contributions,
            "_narrative_listing": {
                "listing_id": str(uuid4()),
                "price_value": 999.0,
                "price_currency": "USD",
                "price_changes": (),
            },
        },
    )

    context.service.get_narrative(
        owner_id=owner_id, profile_id=profile_id, run_id=run_id, listing_id=listing_id
    )

    assert writer.contexts[-1].listing == {}


def test_narrative_ignores_identityless_frozen_observation() -> None:
    context, writer, owner_id, profile_id, run_id, listing_id = _context()
    item = context.items.items_by_run[run_id][0]
    context.items.items_by_run[run_id][0] = replace(
        item,
        contributions={
            **item.contributions,
            "_narrative_observations": {
                "luminosidad": {
                    "observation_id": str(uuid4()),
                    "concept_key": "luminosidad",
                    "matcher_type": "signal_score",
                    "value": 0.8,
                    "score": 0.8,
                    "confidence": 0.8,
                    "evidence": {
                        "signal_ref": "transit_access",
                        "contributors": [
                            {
                                "term": "subway_station.nearest_m",
                                "observed_value": 300,
                                "unit": "m",
                            }
                        ],
                    },
                    "source": "urban",
                    "state": "active",
                }
            },
        },
    )

    context.service.get_narrative(
        owner_id=owner_id, profile_id=profile_id, run_id=run_id, listing_id=listing_id
    )

    assert writer.contexts[-1].geography == ()
