"""Pure deterministic explanation builder.

Explanations are generated from the frozen run data (evaluations, policy and
templates). Copy is template-based: 0 generative text in v1 and 0 claims
without an internal evidence ref (FR-012/FR-013, SC-007).
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from umbral.application.scoring.contracts import (
    CriterionEvaluation,
    EvidenceLevel,
    Explanation,
    ExplanationReason,
    ExplanationRisk,
)
from umbral.application.scoring.policy import ScoringPolicyDoc

_DISPLAY_LABELS = {
    "presupuesto": "el presupuesto",
    "ambientes": "los ambientes",
    "superficie": "la superficie",
    "ubicacion": "la ubicación",
    "balcon": "el balcón",
    "luminosidad": "la luz natural",
    "estado_general": "el estado general",
    "proximidad_cafes": "cafés cercanos",
    "acceso_transporte": "acceso al transporte",
    "calma_residencial": "calma residencial",
    "ruido_ambiental": "ruido ambiental",
}


def evidence_level(confidence: float, policy: ScoringPolicyDoc) -> EvidenceLevel:
    if confidence >= policy.confidence.get("strong_threshold", 0.8):
        return "strong"
    if confidence >= policy.confidence.get("medium_threshold", 0.5):
        return "medium"
    return "low"


def build_explanation(
    *,
    search_profile_id: UUID,
    run_id: UUID,
    listing_id: UUID,
    score: float,
    confidence: float,
    evaluations: tuple[CriterionEvaluation, ...],
    policy: ScoringPolicyDoc,
    templates: Mapping[str, str],
    satisfied_filters: tuple[str, ...],
    profile_version_id: UUID,
    active_criterion_keys: frozenset[str] | None = None,
) -> Explanation:
    """Build the explanation document from frozen evaluations."""

    if active_criterion_keys is not None:
        evaluations = tuple(
            evaluation
            for evaluation in evaluations
            if evaluation.criterion_key in active_criterion_keys
        )

    reasons: list[ExplanationReason] = []
    risks: list[ExplanationRisk] = []
    missing: list[str] = []
    for evaluation in evaluations:
        level = evidence_level(evaluation.confidence, policy)
        text = _template_text(
            evaluation.reason_code,
            templates,
            concept=_display_label(evaluation.criterion_key),
            criterion=_display_label(evaluation.criterion_key),
            confidence=f"{evaluation.confidence:.2f}",
        )
        if evaluation.state == "unknown":
            missing.append(evaluation.criterion_key)
            risks.append(
                ExplanationRisk(
                    criterion_key=evaluation.criterion_key,
                    state="unknown",
                    reason_code=evaluation.reason_code,
                    text=text,
                )
            )
            continue
        reasons.append(
            ExplanationReason(
                criterion_key=evaluation.criterion_key,
                state=evaluation.state,
                score=evaluation.score,
                confidence=evaluation.confidence,
                contribution=evaluation.contribution,
                evidence_level=level,
                reason_code=evaluation.reason_code,
                evidence_refs=evaluation.evidence_refs,
                text=text,
            )
        )
        if evaluation.confidence < policy.confidence.get("medium_threshold", 0.5):
            risks.append(
                ExplanationRisk(
                    criterion_key=evaluation.criterion_key,
                    state=evaluation.state,
                    reason_code=evaluation.reason_code,
                    text=text,
                )
            )
    reasons.sort(
        key=lambda reason: (
            -reason.contribution,
            -reason.score,
            reason.criterion_key,
        )
    )
    deduped_risks = _dedupe_risks(tuple(risks))
    return Explanation(
        search_profile_id=search_profile_id,
        run_id=run_id,
        listing_id=listing_id,
        score_version=policy.score_policy_version,
        score=score,
        confidence=confidence,
        reasons=tuple(reasons),
        risks=deduped_risks,
        missing_data=tuple(missing),
        satisfied_filters=satisfied_filters,
        profile_snapshot={
            "profile_version_id": str(profile_version_id),
            "policy_version_id": policy.score_policy_version,
        },
        feature_snapshot={
            "evaluation_version_key": f"run:{run_id}:listing:{listing_id}",
        },
    )


def _template_text(
    reason_code: str,
    templates: Mapping[str, str],
    **values: str,
) -> str:
    key = f"reason.{reason_code}"
    text = templates.get(key, reason_code)
    for name, value in values.items():
        text = text.replace("{" + name + "}", value)
    return text


def _display_label(criterion_key: str) -> str:
    return _DISPLAY_LABELS.get(criterion_key, "este criterio")


def _dedupe_risks(risks: tuple[ExplanationRisk, ...]) -> tuple[ExplanationRisk, ...]:
    seen: set[tuple[str, str]] = set()
    deduped: list[ExplanationRisk] = []
    for risk in risks:
        identity = (risk.criterion_key, risk.state)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(risk)
    return tuple(deduped)
