# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Canonical preference vocabulary resolution tests (D-03, T004)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import pytest

from umbral.application.agent.tools.preferences import (
    PreferenceUnknownConcept,
    PreferenceVocabularyInvalid,
    parse_preference_vocabulary,
)

_VALID: dict[str, Any] = {
    "registry_version": "preferences-vocabulary-v1",
    "schema_version": "preferences-v1",
    "entries": [
        {
            "aliases": ["luminoso", "con luz"],
            "concept_key": "luminosidad",
            "polarity": "positive",
            "value": None,
        },
        {
            "aliases": ["con balcon"],
            "concept_key": "balcon",
            "polarity": "positive",
            "value": None,
        },
        {
            "aliases": ["cocina separada"],
            "concept_key": "tipo_cocina",
            "polarity": "positive",
            "value": "separada",
        },
    ],
}


def _spec(**overrides):
    data = dict(_VALID)
    data.update(overrides)
    return parse_preference_vocabulary(data)


def test_resolves_alias_exact_case_insensitive() -> None:
    spec = _spec()
    intent = spec.resolve("Luminoso")
    assert intent.concept_key == "luminosidad"
    assert intent.polarity == "positive"
    assert spec.resolve("con luz").concept_key == "luminosidad"


def test_resolves_accents_in_natural_phrases() -> None:
    spec = parse_preference_vocabulary(
        {
            "registry_version": "preferences-vocabulary-v1",
            "schema_version": "preferences-v1",
            "entries": [
                {
                    "aliases": ["cerca de cafes"],
                    "concept_key": "proximidad_cafes",
                    "polarity": "positive",
                    "value": None,
                }
            ],
        }
    )

    assert spec.resolve("cerca de cafés").concept_key == "proximidad_cafes"


def test_resolve_normalizes_whitespace() -> None:
    spec = _spec()
    assert spec.resolve("  con   balcon ").concept_key == "balcon"


def test_resolves_alias_embedded_in_a_longer_phrase() -> None:
    spec = _spec()
    assert spec.resolve("quiero un depto luminoso").concept_key == "luminosidad"
    assert spec.resolve("depto luminoso").concept_key == "luminosidad"
    assert spec.resolve("quisiera un depto con luz natural").concept_key == (
        "luminosidad"
    )


def test_resolves_compound_alias_embedded_in_a_phrase() -> None:
    spec = parse_preference_vocabulary(
        {
            "registry_version": "preferences-vocabulary-v1",
            "schema_version": "preferences-v1",
            "entries": [
                {
                    "aliases": ["cerca de cafes", "cerca de un cafe"],
                    "concept_key": "proximidad_cafes",
                    "polarity": "positive",
                    "value": None,
                }
            ],
        }
    )
    assert (
        spec.resolve("quiero un depto cerca de un cafe").concept_key
        == "proximidad_cafes"
    )
    assert spec.resolve("cerca de cafes").concept_key == "proximidad_cafes"


def test_embedded_match_prefers_the_longest_alias() -> None:
    spec = _spec()
    assert spec.resolve("cocina separada y luminosa").concept_key == "tipo_cocina"


def test_resolve_keeps_value_for_categorical() -> None:
    spec = _spec()
    assert spec.resolve("cocina separada").value == "separada"


def test_resolve_unknown_phrase_raises_actionable_error() -> None:
    spec = _spec()
    with pytest.raises(PreferenceUnknownConcept) as excinfo:
        spec.resolve("cerca del subte")
    assert excinfo.value.code == "preference.unknown_concept"
    assert excinfo.value.phrase == "cerca del subte"


def test_resolve_empty_phrase_raises() -> None:
    spec = _spec()
    with pytest.raises(PreferenceUnknownConcept):
        spec.resolve("   ")


def test_parse_rejects_unknown_registry() -> None:
    with pytest.raises(PreferenceVocabularyInvalid):
        _spec(registry_version="nope")


def test_parse_rejects_invalid_polarity() -> None:
    entries = [
        dict(
            _VALID["entries"][0],
            polarity="neutral",
        )
    ]
    with pytest.raises(PreferenceVocabularyInvalid):
        _spec(entries=entries)


def test_parse_rejects_duplicate_alias() -> None:
    entries = list(_VALID["entries"]) + [
        dict(_VALID["entries"][0], aliases=["luminoso", "luminosa"])
    ]
    with pytest.raises(PreferenceVocabularyInvalid):
        _spec(entries=entries)


def test_parse_rejects_non_string_value() -> None:
    entries = [dict(_VALID["entries"][0], value=5)]
    with pytest.raises(PreferenceVocabularyInvalid):
        _spec(entries=entries)


class _FakeConcepts:
    def get(self, concept_key: str) -> tuple[object, str] | None:
        if concept_key == "luminosidad":
            return (object(), concept_key)
        return None


class _FakeFacts:
    def __init__(self) -> None:
        self.active: tuple[object, ...] = ()


class _FakePolicies:
    def latest_version(self, key: str) -> object | None:
        return _Version()


class _Version:
    version_id = object()
    contract_version = "1"


def _preference_service(active_fact: object | None = None):
    """Minimal FeedbackService surface for propose_preference (D-02/D-04)."""
    from umbral.application.events.registry import EventsRegistrySpec
    from umbral.application.feedback.contracts import (
        LearningPolicyDoc,
        QuickReasonsSpec,
    )
    from umbral.application.feedback.ports import (
        ConceptReader,
        EventWriter,
        FactReader,
        FeedbackEventRepository,
        LearningPolicyRepository,
        LearningProposalRepository,
        ListingReader,
        ProfileReader,
        ShortlistPort,
    )
    from umbral.application.feedback.service import FeedbackService

    class _Facts:
        def active_for_profile(self, profile_id):
            return (active_fact,) if active_fact is not None else ()

    class _Policy:
        default_suggested_weight = 0.5
        default_suggested_confidence = 0.7
        proposal_expiration_days = 7
        window_days = 30
        cooldown_days = 14

    class _Repo:
        def __init__(self) -> None:
            self.inserted: list[object] = []

        def insert(self, proposal) -> None:
            self.inserted.append(proposal)

        def pending_for_concept(self, profile_id, concept_id) -> object | None:
            return None

    repo = _Repo()
    service = FeedbackService(
        events=cast(FeedbackEventRepository, object()),
        policies=cast(LearningPolicyRepository, _FakePolicies()),
        proposals=cast(LearningProposalRepository, repo),
        shortlists=cast(ShortlistPort, object()),
        profiles=cast(ProfileReader, object()),
        listings=cast(ListingReader, object()),
        concepts=cast(ConceptReader, _FakeConcepts()),
        facts=cast(FactReader, _Facts()),
        events_out=cast(EventWriter, object()),
        events_registry=cast(EventsRegistrySpec, object()),
        reasons=cast(QuickReasonsSpec, object()),
        policy_seed={},
        policy_seed_version="learning-policy-v1",
        clock=lambda: datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc),
    )
    service._owned = lambda owner_id, profile_id: type(  # type: ignore[method-assign]
        "P", (), {"profile_id": profile_id, "status": "active"}
    )()
    service.latest_learning_document = lambda: LearningPolicyDoc(  # type: ignore[method-assign]
        contract_version="1",
        learning_policy_version="learning-policy-v1",
        min_signals=1,
        window_days=30,
        min_signal_confidence=0.7,
        cooldown_days=14,
        proposal_expiration_days=7,
        default_suggested_weight=0.5,
        default_suggested_confidence=0.7,
    )
    service._emit_server_event = lambda **kwargs: None  # type: ignore[method-assign]
    return service, repo


class _ActiveFact:
    concept_key = "luminosidad"
    polarity = "negative"
    weight = 0.5
    confidence = 0.8
    fact_source = "learning.confirm"
    value = None
    created_at = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def test_propose_preference_detects_contradiction_with_active_fact() -> None:
    from umbral.application.feedback.contracts import LearningProposal

    service, repo = _preference_service(active_fact=_ActiveFact())
    proposal, impact = service.propose_preference(
        owner_id=object(),
        profile_id=object(),
        concept_key="luminosidad",
        polarity="positive",
        value=None,
        correlation_id=object(),
    )
    assert isinstance(proposal, LearningProposal)
    assert proposal.state == "pending"
    assert impact.contradicts is True
    assert impact.current is not None
    assert impact.current["polarity"] == "negative"
    assert len(repo.inserted) == 1


def test_propose_preference_without_fact_has_no_contradiction() -> None:
    service, repo = _preference_service()
    proposal, impact = service.propose_preference(
        owner_id=object(),
        profile_id=object(),
        concept_key="luminosidad",
        polarity="positive",
        value=None,
        correlation_id=object(),
    )
    assert impact.contradicts is False
    assert impact.current is None
    assert len(repo.inserted) == 1


def test_propose_preference_rejects_unknown_concept() -> None:
    from umbral.application.feedback.contracts import FeedbackValidationError

    service, _ = _preference_service()
    try:
        service.propose_preference(
            owner_id=object(),
            profile_id=object(),
            concept_key="subte",
            polarity="positive",
            value=None,
            correlation_id=object(),
        )
    except FeedbackValidationError as error:
        assert "preference.unknown_concept" in error.error_codes
        return
    raise AssertionError("unknown concept must be rejected")


def test_active_preferences_lists_facts() -> None:
    service, _ = _preference_service(active_fact=_ActiveFact())
    facts = service.active_preferences(owner_id=object(), profile_id=object())
    assert len(facts) == 1
    assert facts[0].concept_key == "luminosidad"


def test_propose_preference_removal_creates_pending_proposal() -> None:
    service, repo = _preference_service(active_fact=_ActiveFact())
    proposal, impact = service.propose_preference_removal(
        owner_id=object(),
        profile_id=object(),
        concept_key="luminosidad",
        correlation_id=object(),
    )
    assert proposal.state == "pending"
    assert proposal.change.concept_key == "luminosidad"
    assert proposal.change.polarity == "negative"
    assert impact.current is not None
    assert len(repo.inserted) == 1


def test_propose_preference_removal_rejects_inactive_concept() -> None:
    from umbral.application.feedback.contracts import FeedbackValidationError

    service, _ = _preference_service()
    try:
        service.propose_preference_removal(
            owner_id=object(),
            profile_id=object(),
            concept_key="luminosidad",
            correlation_id=object(),
        )
    except FeedbackValidationError as error:
        assert "preference.not_active" in error.error_codes
        return
    raise AssertionError("inactive preference removal must be rejected")


def test_requires_value_intent_is_exposed() -> None:
    entries = list(_VALID["entries"]) + [
        {
            "aliases": ["la cocina", "tipo de cocina"],
            "concept_key": "tipo_cocina",
            "polarity": "positive",
            "value": None,
            "requires_value": True,
        }
    ]
    spec = _spec(entries=entries)
    assert spec.resolve("la cocina").requires_value is True
    assert spec.resolve("cocina separada").requires_value is False
