"""US3: rule extraction pipeline publishes observations with evidence."""

from __future__ import annotations

from uuid import uuid4

from tests.support.criteria import CriteriaTestContext

from umbral.application.criteria.contracts import RecomputeScope


def _seed_with_listings(context: CriteriaTestContext, texts: list[str]) -> None:
    context.seed_concepts()
    for text in texts:
        context.add_listing(description_text=text)


def test_process_extraction_publishes_rule_observations() -> None:
    context = CriteriaTestContext()
    _seed_with_listings(
        context,
        [
            "Departamento con balcon y cocina separada.",
            "Monoambiente sin balcon.",
            "Piso luminoso.",
        ],
    )
    summary = context.service.process_extraction(
        RecomputeScope("concept", "balcon"), job_execution_id=uuid4()
    )
    assert summary["published"] == 3
    observations = [
        item for item in context.observations.rows if item.concept_key == "balcon"
    ]
    assert len(observations) == 3
    assert all(item.state == "active" for item in observations)
    assert all(item.source == "rule" for item in observations)
    assert all(item.extraction_version_id is not None for item in observations)
    values = [item.value for item in observations]
    assert values.count("true") == 1
    assert values.count("false") == 1
    assert values.count(None) == 1
    no_evidence = next(item for item in observations if item.value is None)
    assert no_evidence.evidence["fragment"] is None
    assert no_evidence.score == 0.0


def test_process_extraction_registers_rule_versions() -> None:
    context = CriteriaTestContext()
    _seed_with_listings(context, ["con balcon"])
    context.service.process_extraction(
        RecomputeScope("concept", "balcon"), job_execution_id=uuid4()
    )
    version = context.extraction_versions.find("rule", "balcon", "balcon.rule-v1")
    assert version is not None
    assert version.payload["rule"] == "balcon"


def test_process_extraction_batch_event_carries_counts() -> None:
    context = CriteriaTestContext()
    _seed_with_listings(context, ["con balcon", "sin balcon"])
    context.service.process_extraction(
        RecomputeScope("concept", "balcon"), job_execution_id=uuid4()
    )
    events = [
        item
        for item in context.events.events
        if item.event_type == "criteria.observation_batch_published.v1"
    ]
    assert len(events) == 1
    assert events[0].payload["published_count"] == 2
    assert events[0].payload["scope_key"] == "balcon"


def test_full_scope_extracts_all_seed_concepts() -> None:
    context = CriteriaTestContext()
    _seed_with_listings(context, ["Departamento con balcon y cocina separada."])
    summary = context.service.process_extraction(
        RecomputeScope("full", None), job_execution_id=uuid4()
    )
    assert summary["concept_count"] == 9
    concept_keys = {item.concept_key for item in context.observations.rows}
    assert concept_keys == {
        "balcon",
        "ambientes",
        "piso",
        "tipo_cocina",
        "luminosidad",
        "estado_general",
        "moderno",
        "proximidad_cafes",
        "acceso_transporte",
    }
