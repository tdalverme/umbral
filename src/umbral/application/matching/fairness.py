"""Pure forbidden-features registry validation and normative-phrase scan.

The fairness review (UM-H3-035) publishes the machine-checkable registry
``contracts/matching/v1/forbidden-features-v1.json`` plus a human document.
Every forbidden concept must also be ``compute_policy.computable: false`` in
the concepts seed; the phrase scan rejects normative copy in templates
(FR-008/FR-009, research R-05).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from umbral.application.matching.contracts import (
    ForbiddenConcept,
    ForbiddenFeatures,
    ForbiddenProxy,
    MatchingValidationError,
)


def load_forbidden_features(path: Path) -> ForbiddenFeatures:
    """Load and validate the forbidden-features registry from a file path."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise MatchingValidationError(("matching.forbidden_required",))
    return parse_forbidden_features(raw)


def parse_forbidden_features(
    data: Mapping[str, object],
) -> ForbiddenFeatures:
    """Parse and validate the forbidden-features document."""
    errors: list[str] = []
    if data.get("contract_version") != "1":
        errors.append("matching.unsupported_contract_version")
    if data.get("registry_version") != "forbidden-features-v1":
        errors.append("matching.registry_version_required")
    concepts = _parse_concepts(data.get("forbidden_concepts"), errors)
    proxies = _parse_proxies(data.get("forbidden_proxies"), errors)
    raw_phrases = data.get("normative_phrases")
    phrases = (
        tuple(str(item) for item in raw_phrases)
        if isinstance(raw_phrases, list)
        else ()
    )
    if not phrases:
        errors.append("matching.normative_phrases_required")
    if errors:
        raise MatchingValidationError(tuple(sorted(set(errors))))
    return ForbiddenFeatures(
        contract_version="1",
        registry_version="forbidden-features-v1",
        forbidden_concepts=concepts,
        forbidden_proxies=proxies,
        normative_phrases=phrases,
    )


def validate_seed_linkage(
    forbidden: ForbiddenFeatures, computable: Mapping[str, bool]
) -> tuple[str, ...]:
    """Return errors for forbidden concepts not marked non-computable."""
    return tuple(
        f"matching.forbidden_must_be_non_computable:{concept.concept_key}"
        for concept in forbidden.forbidden_concepts
        if computable.get(concept.concept_key, True)
    )


def scan_normative_phrases(
    templates: Mapping[str, str],
    forbidden: ForbiddenFeatures,
) -> tuple[str, ...]:
    """Return template keys whose text contains a forbidden normative phrase."""
    flagged: list[str] = []
    lowered_phrases = tuple(phrase.casefold() for phrase in forbidden.normative_phrases)
    for key, text in templates.items():
        lowered = text.casefold()
        if any(phrase in lowered for phrase in lowered_phrases):
            flagged.append(key)
    return tuple(sorted(flagged))


def _parse_concepts(raw: object, errors: list[str]) -> tuple[ForbiddenConcept, ...]:
    if not isinstance(raw, list):
        errors.append("matching.forbidden_concepts_required")
        return ()
    concepts: list[ForbiddenConcept] = []
    for item in raw:
        if not isinstance(item, Mapping):
            errors.append("matching.forbidden_concept_invalid_shape")
            continue
        concept_key = item.get("concept_key")
        justification = item.get("justification")
        if not isinstance(concept_key, str) or not concept_key:
            errors.append("matching.forbidden_concept_key_required")
            continue
        concepts.append(
            ForbiddenConcept(
                concept_key=concept_key,
                justification=(
                    str(justification) if isinstance(justification, str) else ""
                ),
            )
        )
    return tuple(concepts)


def _parse_proxies(raw: object, errors: list[str]) -> tuple[ForbiddenProxy, ...]:
    if not isinstance(raw, list):
        errors.append("matching.forbidden_proxies_required")
        return ()
    proxies: list[ForbiddenProxy] = []
    for item in raw:
        if not isinstance(item, Mapping):
            errors.append("matching.forbidden_proxy_invalid_shape")
            continue
        proxy_key = item.get("proxy_key")
        justification = item.get("justification")
        if not isinstance(proxy_key, str) or not proxy_key:
            errors.append("matching.forbidden_proxy_key_required")
            continue
        proxies.append(
            ForbiddenProxy(
                proxy_key=proxy_key,
                justification=(
                    str(justification) if isinstance(justification, str) else ""
                ),
            )
        )
    return tuple(proxies)
