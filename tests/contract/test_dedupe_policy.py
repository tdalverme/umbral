"""Conformance of the dedupe policy and its evaluator."""

from __future__ import annotations

import json
from pathlib import Path

from tests.support.silver import listing_from_payload, load_records
from umbral.application.silver.dedupe_policy import (
    evaluate_pair,
    parse_dedupe_policy,
    strong_fingerprint,
)
from umbral.infrastructure.silver.contract_loader import load_dedupe_policy

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "contracts" / "dedupe" / "v1" / "dedupe-policy.json"

POLICY = load_dedupe_policy(POLICY_PATH)


def _record(external_id: str) -> dict[str, object]:
    return next(
        r
        for r in load_records("reference-batch.json")
        if r["external_id"] == external_id
    )


def test_policy_document_matches_the_published_json() -> None:
    published = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    parsed = parse_dedupe_policy(published)
    assert parsed.dedupe_policy_version == "dedupe-policy-v1"
    assert "price_value" in parsed.strong_fields
    assert parsed.proposal.threshold == 0.6


def test_same_chain_is_not_evaluated() -> None:
    a = listing_from_payload(_record("sil-0001"))
    b = listing_from_payload(_record("sil-0001"), source_id="source-a")
    result = evaluate_pair(a, b, POLICY)
    assert result.method is None


def test_identical_strong_fields_produce_deterministic_link() -> None:
    a = listing_from_payload(_record("sil-0001"), source_id="source-a")
    b = listing_from_payload(_record("sil-0001"), source_id="source-b")
    result = evaluate_pair(a, b, POLICY)
    assert result.method == "deterministic"
    assert result.state == "confirmed"
    assert result.fingerprint is not None
    fingerprint, _ = strong_fingerprint(a, POLICY)
    assert fingerprint == result.fingerprint


def test_strong_field_difference_degrades_to_proposal_or_nothing() -> None:
    a = listing_from_payload(_record("sil-0001"), source_id="source-a")
    changed = dict(_record("sil-0001"))
    changed["price"] = 900000
    b = listing_from_payload(changed, source_id="source-b")
    result = evaluate_pair(a, b, POLICY)
    assert result.method != "deterministic"
    if result.method == "proposal":
        assert result.state == "pending"
        assert result.score is not None and 0.0 <= result.score <= 1.0
        assert "dimensions" in result.evidence


def test_missing_strong_field_never_auto_merges() -> None:
    a = listing_from_payload(_record("sil-0001"), source_id="source-a")
    missing = dict(_record("sil-0001"))
    missing["surface_m2"] = None
    b = listing_from_payload(missing, source_id="source-b")
    result = evaluate_pair(a, b, POLICY)
    assert result.method != "deterministic"


def test_similar_address_with_price_delta_scores_above_threshold() -> None:
    a = listing_from_payload(_record("sil-0001"), source_id="source-a")
    similar = dict(_record("sil-0001"))
    similar["price"] = 880000
    b = listing_from_payload(similar, source_id="source-b")
    result = evaluate_pair(a, b, POLICY)
    assert result.method == "proposal"
    assert result.score is not None and result.score >= POLICY.proposal.threshold
