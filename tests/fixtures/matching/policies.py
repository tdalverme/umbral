"""Shared policy builders for the matching regression conformance."""

from __future__ import annotations

from collections.abc import Mapping

from umbral.application.scoring.policy import ScoringPolicyDoc, parse_policy_document
from umbral.infrastructure.criteria.contract_loader import load_matcher_types

_MATCHER_TYPES = load_matcher_types()


def _policy(
    score_policy_version: str,
    presupuesto_weight: float,
    ambientes_weight: float,
    superficie_weight: float,
) -> ScoringPolicyDoc:
    data: Mapping[str, object] = {
        "contract_version": "1",
        "score_policy_version": score_policy_version,
        "normalization": "weighted_sum",
        "score_round": 4,
        "confidence": {
            "unknown_penalty": 0.2,
            "strong_threshold": 0.8,
            "medium_threshold": 0.5,
        },
        "criteria": [
            {
                "key": "presupuesto",
                "concept": "presupuesto",
                "matcher_type": "numeric_range",
                "weight": presupuesto_weight,
                "params": {"min": 0, "max": 1},
                "gate": None,
            },
            {
                "key": "ambientes",
                "concept": "ambientes",
                "matcher_type": "numeric_range",
                "weight": ambientes_weight,
                "params": {"min": 0, "max": 200},
                "gate": None,
            },
            {
                "key": "superficie",
                "concept": "superficie",
                "matcher_type": "numeric_range",
                "weight": superficie_weight,
                "params": {"min": 0, "max": 2000},
                "gate": None,
            },
        ],
        "bonuses": [],
        "penalties": [],
        "tie_break": ["score", "total_cost_asc", "listing_id_asc"],
    }
    return parse_policy_document(data, _MATCHER_TYPES)


def baseline_policy() -> ScoringPolicyDoc:
    """Ambientes-dominant: test-a (rooms == min) beats test-b."""
    return _policy("scoring-policy-test-v1", 0.2, 0.6, 0.2)


def candidate_policy() -> ScoringPolicyDoc:
    """Presupuesto-dominant: test-b (cheaper) beats test-a -> order change."""
    return _policy("scoring-policy-test-v2", 0.6, 0.2, 0.2)
