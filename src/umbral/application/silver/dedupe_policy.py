"""Pure loader and evaluator for the published dedupe policy.

The rule set is loaded from ``contracts/dedupe/v1/dedupe-policy.json`` by an
infrastructure loader and passed in as a :class:`DedupePolicySpec`. Evaluation is
deterministic, non-destructive and never auto-merges ambiguous cases.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass

from umbral.application.silver.contracts import (
    DedupeLinkState,
    DedupeMethod,
    NormalizedListing,
)

_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class DimensionSpec:
    name: str
    weight: float


@dataclass(frozen=True, slots=True)
class ProposalSpec:
    threshold: float
    dimensions: tuple[DimensionSpec, ...]


@dataclass(frozen=True, slots=True)
class DedupePolicySpec:
    policy_version: str
    dedupe_policy_version: str
    strong_fields: tuple[str, ...]
    proposal: ProposalSpec
    states: tuple[str, ...]
    evidence_required: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PairEvaluation:
    method: DedupeMethod | None
    state: DedupeLinkState | None
    fingerprint: str | None
    score: float | None
    evidence: Mapping[str, object]


def parse_dedupe_policy(data: Mapping[str, object]) -> DedupePolicySpec:
    policy_version = data.get("policy_version")
    if policy_version != "1":
        raise ValueError("unsupported dedupe policy document version")
    dedupe_policy_version = data.get("dedupe_policy_version")
    if not isinstance(dedupe_policy_version, str) or not dedupe_policy_version:
        raise ValueError("dedupe_policy_version is required")

    raw_strong = data.get("strong_fields")
    if not isinstance(raw_strong, list) or not raw_strong:
        raise ValueError("strong_fields are required")
    strong_fields = tuple(str(item) for item in raw_strong)

    raw_proposal = data.get("proposal")
    if not isinstance(raw_proposal, Mapping):
        raise ValueError("proposal rules are required")
    threshold = raw_proposal.get("threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise ValueError("proposal threshold must be a number")
    raw_dimensions = raw_proposal.get("dimensions")
    if not isinstance(raw_dimensions, list) or not raw_dimensions:
        raise ValueError("proposal dimensions are required")
    dimensions: list[DimensionSpec] = []
    for raw in raw_dimensions:
        if not isinstance(raw, Mapping):
            raise ValueError("proposal dimension must be an object")
        name = raw.get("name")
        weight = raw.get("weight")
        if not isinstance(name, str) or not name:
            raise ValueError("proposal dimension name is required")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            raise ValueError("proposal dimension weight must be a number")
        dimensions.append(DimensionSpec(name=name, weight=float(weight)))

    raw_states = data.get("states")
    states = (
        tuple(str(item) for item in raw_states) if isinstance(raw_states, list) else ()
    )
    raw_evidence = data.get("evidence_required")
    evidence_required = (
        tuple(str(item) for item in raw_evidence)
        if isinstance(raw_evidence, list)
        else ()
    )

    return DedupePolicySpec(
        policy_version=str(policy_version),
        dedupe_policy_version=str(dedupe_policy_version),
        strong_fields=strong_fields,
        proposal=ProposalSpec(threshold=float(threshold), dimensions=tuple(dimensions)),
        states=states,
        evidence_required=evidence_required,
    )


def strong_fingerprint(
    listing: NormalizedListing, spec: DedupePolicySpec
) -> tuple[str | None, tuple[str, ...]]:
    """Return (fingerprint, missing_fields) from the strong-field tuple."""
    values: list[str] = []
    missing: list[str] = []
    for field in spec.strong_fields:
        value = _strong_value(listing, field)
        if value is None:
            missing.append(field)
            values.append("")
        else:
            values.append(value)
    if missing:
        return None, tuple(missing)
    digest = hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()
    return digest, ()


def evaluate_pair(
    a: NormalizedListing, b: NormalizedListing, spec: DedupePolicySpec
) -> PairEvaluation:
    """Evaluate one cross-chain pair; never merges ambiguous cases."""
    if _same_chain(a, b):
        return PairEvaluation(None, None, None, None, {})
    fingerprint, missing = strong_fingerprint(a, spec)
    fingerprint_b, missing_b = strong_fingerprint(b, spec)
    if fingerprint is not None and fingerprint_b is not None:
        if fingerprint == fingerprint_b:
            return PairEvaluation(
                method="deterministic",
                state="confirmed",
                fingerprint=fingerprint,
                score=None,
                evidence=_deterministic_evidence(a, b, fingerprint),
            )
    if missing or missing_b:
        return PairEvaluation(None, None, None, None, {"degraded": True})

    dimensions, score = _proposal_score(a, b, spec)
    if not dimensions:
        return PairEvaluation(None, None, None, None, {})
    if score < spec.proposal.threshold:
        return PairEvaluation(
            None, None, None, None, {"dimensions": dimensions, "score": score}
        )
    return PairEvaluation(
        method="proposal",
        state="pending",
        fingerprint=None,
        score=round(score, 4),
        evidence={"dimensions": dimensions, "score": round(score, 4)},
    )


def _deterministic_evidence(
    a: NormalizedListing, b: NormalizedListing, fingerprint: str
) -> Mapping[str, object]:
    return {
        "version": "dedupe-policy-v1",
        "method": "deterministic",
        "fingerprint": fingerprint,
        "fields": {
            "operation": a.operation,
            "property_type": a.property_type,
            "price_value": a.price_value,
            "price_currency": a.price_currency,
            "surface_m2": a.surface_m2,
            "rooms": a.rooms,
            "bedrooms": a.bedrooms,
            "neighborhood": a.neighborhood,
        },
        "source_rows": [str(a.snapshot_id), str(b.snapshot_id)],
    }


def _proposal_score(
    a: NormalizedListing, b: NormalizedListing, spec: DedupePolicySpec
) -> tuple[dict[str, float], float]:
    scores: dict[str, float] = {}
    weights: dict[str, float] = {}
    for dimension in spec.proposal.dimensions:
        value = _dimension_score(dimension.name, a, b)
        if value is None:
            continue
        scores[dimension.name] = round(value, 4)
        weights[dimension.name] = dimension.weight
    if not scores:
        return {}, 0.0
    total_weight = sum(weights.values())
    score = sum(scores[name] * weights[name] for name in scores) / total_weight
    return scores, score


def _dimension_score(
    name: str, a: NormalizedListing, b: NormalizedListing
) -> float | None:
    if name == "address_tokens":
        return _jaccard(a.location_text, b.location_text)
    if name == "price":
        if (
            a.price_value is None
            or b.price_value is None
            or a.price_currency != b.price_currency
            or a.price_value <= 0
            or b.price_value <= 0
        ):
            return None
        return 1.0 - min(a.price_value, b.price_value) / max(
            a.price_value, b.price_value
        )
    if name == "surface":
        if a.surface_m2 is None or b.surface_m2 is None:
            return None
        a_surface, b_surface = a.surface_m2, b.surface_m2
        if a_surface <= 0 or b_surface <= 0:
            return None
        return 1.0 - min(a_surface, b_surface) / max(a_surface, b_surface)
    if name == "rooms":
        if a.rooms is None or b.rooms is None:
            return None
        diff = abs(a.rooms - b.rooms)
        if diff == 0:
            return 1.0
        if diff == 1:
            return 0.5
        return 0.0
    return None


def _jaccard(a: str, b: str) -> float | None:
    tokens_a = set(_WORD_RE.findall(a.lower()))
    tokens_b = set(_WORD_RE.findall(b.lower()))
    if not tokens_a and not tokens_b:
        return None
    union = tokens_a | tokens_b
    if not union:
        return None
    return len(tokens_a & tokens_b) / len(union)


def _same_chain(a: NormalizedListing, b: NormalizedListing) -> bool:
    return a.source.source_id == b.source.source_id and a.external_id == b.external_id


def _strong_value(listing: NormalizedListing, field: str) -> str | None:
    if field == "operation":
        return listing.operation
    if field == "property_type":
        return listing.property_type
    if field == "price_value":
        return _canonical_number(listing.price_value)
    if field == "price_currency":
        return listing.price_currency
    if field == "surface_m2":
        if listing.surface_m2 is None:
            return None
        return _canonical_number(listing.surface_m2)
    if field == "rooms":
        if listing.rooms is None:
            return None
        return str(listing.rooms)
    if field == "bedrooms":
        if listing.bedrooms is None:
            return None
        return str(listing.bedrooms)
    if field == "neighborhood":
        if listing.neighborhood is None:
            return None
        return " ".join(listing.neighborhood.casefold().split())
    return None


def _canonical_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return format(float(value), "f")
