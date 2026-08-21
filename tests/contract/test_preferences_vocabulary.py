"""Preference vocabulary contract conformance (014-soft-preferences-chat)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from umbral.application.agent.tools.preferences import (
    PreferenceVocabularyInvalid,
    parse_preference_vocabulary,
)
from umbral.infrastructure.agent.tools.preferences_loader import (
    load_preference_vocabulary,
)

ROOT = Path(__file__).resolve().parents[2]
CONCEPTS = json.loads(
    (ROOT / "contracts" / "criteria" / "v2" / "concepts-seed-v2.json").read_text(
        encoding="utf-8"
    )
)


def test_vocabulary_contract_loads_and_resolves_entries() -> None:
    spec = load_preference_vocabulary()
    assert spec.registry_version == "preferences-vocabulary-v1"
    assert spec.schema_version == "preferences-v1"
    assert len(spec.entries) >= 7
    assert spec.resolve("luminoso").concept_key == "luminosidad"
    assert spec.resolve("LUMINOSO").polarity == "positive"
    assert spec.resolve("con balcon").concept_key == "balcon"
    assert spec.resolve("cocina separada").value == "separada"


def test_vocabulary_entries_reference_published_concepts() -> None:
    spec = load_preference_vocabulary()
    concept_keys = {
        str(concept["key"])
        for concept in CONCEPTS["concepts"]
    }
    for entry in spec.entries:
        assert entry.intent.concept_key in concept_keys, (
            f"concept {entry.intent.concept_key} not in concepts seed"
        )


def test_vocabulary_resolve_unknown_phrase_raises() -> None:
    from umbral.application.agent.tools.preferences import (
        PreferenceUnknownConcept,
    )

    spec = load_preference_vocabulary()
    with pytest.raises(PreferenceUnknownConcept):
        spec.resolve("quiero algo cerca del subte")


def test_vocabulary_rejects_structural_violations() -> None:
    base = json.loads(
        (
            ROOT
            / "contracts"
            / "criteria"
            / "v1"
            / "preferences-vocabulary-v1.json"
        ).read_text(encoding="utf-8")
    )
    bad_registry = dict(base, registry_version="nope")
    with pytest.raises(PreferenceVocabularyInvalid):
        parse_preference_vocabulary(bad_registry)
    bad_polarity = dict(base)
    bad_polarity["entries"] = [
        dict(
            base["entries"][0],
            polarity="neutral",
        )
    ]
    with pytest.raises(PreferenceVocabularyInvalid):
        parse_preference_vocabulary(bad_polarity)
    duplicated = dict(base)
    duplicated["entries"] = list(base["entries"]) + [
        dict(base["entries"][0], aliases=["luminoso", "otro alias"])
    ]
    with pytest.raises(PreferenceVocabularyInvalid):
        parse_preference_vocabulary(duplicated)
