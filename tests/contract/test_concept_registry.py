"""Conformance of the concept registry contracts: seed, matcher types, aliases."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from tests.fixtures.criteria import golden
from umbral.application.criteria.registry import (
    ConceptSeed,
    detect_alias_collisions,
    parse_concepts_seed,
    parse_matcher_types,
    resolve_alias,
    validate_concept_seed,
)
from umbral.infrastructure.criteria.contract_loader import (
    load_concepts_seed,
    load_matcher_types,
)

ROOT = Path(__file__).resolve().parents[2]

SEED = load_concepts_seed()
MATCHER_TYPES = load_matcher_types()


def test_contract_documents_parse_and_match_the_published_contracts() -> None:
    seed_data = json.loads(
        (ROOT / "contracts" / "criteria" / "v1" / "concepts-seed-v1.json").read_text(
            encoding="utf-8"
        )
    )
    matcher_data = json.loads(
        (ROOT / "contracts" / "criteria" / "v1" / "matcher-types-v1.json").read_text(
            encoding="utf-8"
        )
    )
    parsed_seed = parse_concepts_seed(seed_data)
    parsed_types = parse_matcher_types(matcher_data)
    assert parsed_seed.seed_version == "concepts-v1"
    assert parsed_types.registry_version == "matcher-types-v1"
    assert {item.key for item in parsed_seed.concepts} == {
        "balcon",
        "ambientes",
        "piso",
        "tipo_cocina",
        "luminosidad",
        "estado_general",
        "barrio_seguro",
        "moderno",
        "proximidad_cafes",
        "acceso_transporte",
        "proximidad_parque",
        "proximidad_compras",
        "vida_nocturna",
        "zona_comercial",
        "caminabilidad",
        "calma_residencial",
        "ruido_transito",
        "ruido_tren",
        "ruido_ambiental",
    }
    assert set(parsed_types.matcher_types) == {
        "numeric_range",
        "categorical",
        "geo_proximity",
        "semantic_feature",
        "signal_score",
    }


def test_seed_concepts_are_all_valid() -> None:
    for seed in SEED.concepts:
        assert validate_concept_seed(seed, MATCHER_TYPES) == ()


def test_unsupported_matcher_type_is_rejected() -> None:
    seed = next(seed for seed in SEED.concepts if seed.key == "balcon")
    bad = dataclasses.replace(seed, matcher_type="matcher_no_soportado")  # type: ignore[arg-type]
    errors = validate_concept_seed(bad, MATCHER_TYPES)
    assert any("unsupported_matcher_type" in error for error in errors)


def test_invalid_param_for_matcher_type_is_rejected() -> None:
    seed = next(seed for seed in SEED.concepts if seed.key == "balcon")
    bad = dataclasses.replace(seed, params_schema={"radius_m": 500})
    errors = validate_concept_seed(bad, MATCHER_TYPES)
    assert any("invalid_param" in error for error in errors)


def test_alias_resolves_to_canonical_key() -> None:
    by_key = {seed.key: seed for seed in SEED.concepts}
    assert resolve_alias(by_key, "balcon") == "balcon"
    assert resolve_alias(by_key, "cocina") == "tipo_cocina"
    assert resolve_alias(by_key, "inexistente") is None


def test_alias_collisions_are_reported_as_warnings() -> None:
    first = next(seed for seed in SEED.concepts if seed.key == "balcon")
    second = next(seed for seed in SEED.concepts if seed.key == "piso")
    colliding = dataclasses.replace(first, aliases=("terraza",))
    other = dataclasses.replace(second, aliases=("terraza",))
    warnings = detect_alias_collisions({"balcon": colliding, "piso": other})
    assert len(warnings) == 1
    assert "alias_collision" in warnings[0]
    assert detect_alias_collisions({seed.key: seed for seed in SEED.concepts}) == ()


def test_signal_score_concepts_reference_known_urban_signals() -> None:
    """Every seed signal_score concept must point at a signal the urban
    contract actually computes; a typo here would silently produce unknown
    observations for the concept."""
    from umbral.infrastructure.urban.contract_loader import (
        load_urban_contract_published,
    )

    contract = load_urban_contract_published()
    known = {signal.name for signal in contract.signals} | {
        composite.name for composite in contract.composite_signals
    }
    signal_score = [
        seed for seed in SEED.concepts if seed.matcher_type == "signal_score"
    ]
    assert signal_score, "seed must declare at least one signal_score concept"
    for seed in signal_score:
        signal_ref = seed.params_schema.get("signal_ref")
        assert isinstance(signal_ref, str), f"{seed.key} must declare a signal_ref"
        assert signal_ref in known, (
            f"{seed.key} references unknown urban signal {signal_ref}"
        )


def test_urban_batch_wires_every_signal_ref_concept() -> None:
    """The urban batch derives its concept->signal map from the seed; adding a
    signal_score concept must be reflected here or the batch never produces its
    observations."""
    from umbral.infrastructure.urban.composition import _signal_ref_concepts

    assert _signal_ref_concepts() == {
        "proximidad_cafes": "cafe_lifestyle",
        "acceso_transporte": "transit_access",
        "proximidad_parque": "green_access",
        "proximidad_compras": "daily_convenience",
        "vida_nocturna": "nightlife_intensity",
        "zona_comercial": "commercial_intensity",
        "caminabilidad": "walkability",
        "calma_residencial": "residential_calm",
        "ruido_transito": "road_noise",
        "ruido_tren": "rail_noise",
        "ruido_ambiental": "noise_risk",
    }


def test_golden_invalid_concept_is_rejected() -> None:
    invalid = next(item for item in golden.concepts_golden()["invalid_concepts"])
    seed = ConceptSeed(
        key=str(invalid["key"]),
        name=str(invalid["name"]),
        aliases=(),
        matcher_type=str(invalid["matcher_type"]),  # type: ignore[arg-type]
        params_schema={},
        source="seed",
        defaults={},
        compute_policy={},
    )
    assert validate_concept_seed(seed, MATCHER_TYPES) != ()
