"""Relevance boundaries for deterministic match explanations."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from tests.support.scoring import MATCHER_TYPES, SEED, TEMPLATES

from umbral.application.scoring.contracts import CriterionEvaluation
from umbral.application.scoring.explanations import build_explanation
from umbral.application.scoring.policy import parse_policy_document

PROFILE_ID = uuid4()
RUN_ID = uuid4()
LISTING_ID = uuid4()
PROFILE_VERSION_ID = uuid4()
POLICY = parse_policy_document(SEED, MATCHER_TYPES)


def _evaluation(
    criterion_key: str,
    *,
    state: str = "match",
    reason_code: str = "concept_observed",
) -> CriterionEvaluation:
    return CriterionEvaluation(
        evaluation_id=uuid4(),
        run_id=RUN_ID,
        listing_id=LISTING_ID,
        criterion_key=criterion_key,
        criterion_version="policy:scoring-policy-v1",
        matcher_type="categorical",
        params={},
        input_refs=(),
        score=1.0 if state == "match" else 0.0,
        confidence=1.0 if state == "match" else 0.0,
        state=state,  # type: ignore[arg-type]
        contribution=0.1 if state == "match" else 0.0,
        reason_code=reason_code,
        evidence_refs=(
            ({"kind": "observation", "ref": "obs-1"},)
            if state == "match"
            else ()
        ),
        created_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
    )


def test_explanation_hides_unasked_criteria() -> None:
    explanation = build_explanation(
        search_profile_id=PROFILE_ID,
        run_id=RUN_ID,
        listing_id=LISTING_ID,
        score=0.8,
        confidence=0.9,
        evaluations=(
            _evaluation("balcon"),
            _evaluation(
                "estado_general",
                state="unknown",
                reason_code="no_observation_data",
            ),
            _evaluation("luminosidad"),
        ),
        policy=POLICY,
        templates=TEMPLATES,
        satisfied_filters=(),
        profile_version_id=PROFILE_VERSION_ID,
        active_criterion_keys=frozenset({"luminosidad"}),
    )

    assert [reason.criterion_key for reason in explanation.reasons] == ["luminosidad"]
    assert explanation.missing_data == ()
    assert explanation.risks == ()


def test_unknown_is_kept_only_when_the_active_criterion_matters() -> None:
    explanation = build_explanation(
        search_profile_id=PROFILE_ID,
        run_id=RUN_ID,
        listing_id=LISTING_ID,
        score=0.4,
        confidence=0.1,
        evaluations=(
            _evaluation(
                "luminosidad",
                state="unknown",
                reason_code="no_observation_data",
            ),
        ),
        policy=POLICY,
        templates=TEMPLATES,
        satisfied_filters=(),
        profile_version_id=PROFILE_VERSION_ID,
        active_criterion_keys=frozenset({"luminosidad"}),
    )

    assert explanation.missing_data == ("luminosidad",)
    assert explanation.risks[0].criterion_key == "luminosidad"
