"""Pure fidelity evaluator for explanations.

Claims are classified against the persisted H3.2 breakdown (criterion
evaluations with evidence refs): ``supported`` when the claim maps to a
breakdown entry with evidence, ``unsupported`` when no matching entry or no
evidence exists, ``contradiction`` when the claimed state conflicts with the
breakdown. The threshold is strict: 100% supported, 0 unsupported, 0
contradictions (clarification 2026-08-09, FR-006/FR-007). Legacy items without
a breakdown are reported ``no_breakdown`` and never scored (research R-04).
"""

from __future__ import annotations

from umbral.application.matching.contracts import (
    ClaimVerdictItem,
    FidelityClaim,
    FidelityReport,
)
from umbral.application.scoring.contracts import (
    CriterionEvaluation,
    Explanation,
)


def evaluate_fidelity(
    *,
    explanation: Explanation,
    breakdown: tuple[CriterionEvaluation, ...],
) -> FidelityReport:
    """Evaluate every reason/risk claim of an explanation against its breakdown.

    Legacy items (``score_version`` ending in ``-baseline`` or an empty
    breakdown that is declared legacy) are reported ``no_breakdown`` and pass
    without fabricated reasons.
    """
    if _is_legacy(explanation, breakdown):
        return FidelityReport(
            passing=True,
            claims=(),
            missing_uncertainty=(),
            no_breakdown_items=(str(explanation.listing_id),),
            reasons=("legacy_no_breakdown",),
        )

    claims = _claims_from_explanation(explanation)
    by_key = {evaluation.criterion_key: evaluation for evaluation in breakdown}
    verdicts: list[ClaimVerdictItem] = []
    for claim in claims:
        evaluation = by_key.get(claim.criterion_key)
        if evaluation is None:
            verdicts.append(
                ClaimVerdictItem(
                    criterion_key=claim.criterion_key,
                    verdict="unsupported",
                    detail="no_breakdown_entry",
                )
            )
            continue
        if (
            claim.asserted_state is not None
            and evaluation.state != "unknown"
            and claim.asserted_state != evaluation.state
        ):
            verdicts.append(
                ClaimVerdictItem(
                    criterion_key=claim.criterion_key,
                    verdict="contradiction",
                    detail=(
                        f"claimed {claim.asserted_state} but "
                        f"breakdown is {evaluation.state}"
                    ),
                )
            )
            continue
        if not claim.evidence_refs or not evaluation.evidence_refs:
            verdicts.append(
                ClaimVerdictItem(
                    criterion_key=claim.criterion_key,
                    verdict="unsupported",
                    detail="no_evidence_ref",
                )
            )
            continue
        verdicts.append(
            ClaimVerdictItem(
                criterion_key=claim.criterion_key,
                verdict="supported",
                detail="evidence_ref",
            )
        )

    missing_uncertainty = _missing_uncertainty(explanation, breakdown)
    failing = [
        item for item in verdicts if item.verdict in {"unsupported", "contradiction"}
    ]
    passing = not failing and not missing_uncertainty
    reasons: list[str] = []
    if failing:
        criteria = ",".join(item.criterion_key for item in failing)
        reasons.append(f"matching.fidelity_failed:{criteria}")
    if missing_uncertainty:
        reasons.append(
            f"matching.uncertainty_not_declared:{','.join(missing_uncertainty)}"
        )
    return FidelityReport(
        passing=passing,
        claims=tuple(verdicts),
        missing_uncertainty=tuple(missing_uncertainty),
        no_breakdown_items=(),
        reasons=tuple(reasons),
    )


def _claims_from_explanation(explanation: Explanation) -> tuple[FidelityClaim, ...]:
    claims: list[FidelityClaim] = []
    for reason in explanation.reasons:
        claims.append(
            FidelityClaim(
                criterion_key=reason.criterion_key,
                asserted_state=reason.state,
                evidence_refs=reason.evidence_refs,
                text=reason.text,
            )
        )
    for risk in explanation.risks:
        claims.append(
            FidelityClaim(
                criterion_key=risk.criterion_key,
                asserted_state=risk.state,
                evidence_refs=(),
                text=risk.text,
            )
        )
    return tuple(claims)


def _missing_uncertainty(
    explanation: Explanation, breakdown: tuple[CriterionEvaluation, ...]
) -> tuple[str, ...]:
    declared = set(explanation.missing_data)
    declared.update(
        risk.criterion_key for risk in explanation.risks if risk.state == "unknown"
    )
    undeclared: list[str] = []
    for evaluation in breakdown:
        if evaluation.state == "unknown" and evaluation.criterion_key not in declared:
            undeclared.append(evaluation.criterion_key)
        elif (
            evaluation.confidence < 0.5
            and evaluation.state != "unknown"
            and evaluation.criterion_key not in declared
        ):
            undeclared.append(evaluation.criterion_key)
    return tuple(sorted(set(undeclared)))


def _is_legacy(
    explanation: Explanation, breakdown: tuple[CriterionEvaluation, ...]
) -> bool:
    if not breakdown:
        return "baseline" in explanation.score_version
    return False
