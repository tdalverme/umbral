"""Loads the published criteria contracts from the repository contracts tree."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from umbral.application.criteria.extractor import (
    ExtractionContractSpec,
    parse_extraction_contract,
)
from umbral.application.criteria.goldens import (
    ExtractionGolden,
    parse_extraction_goldens,
)
from umbral.application.criteria.registry import (
    ConceptsSeedSpec,
    MatcherTypesSpec,
    parse_concepts_seed,
    parse_matcher_types,
)

_CONCEPTS_SEED_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "criteria"
    / "v2"
    / "concepts-seed-v2.json"
)
_MATCHER_TYPES_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "criteria"
    / "v1"
    / "matcher-types-v1.json"
)
_EXTRACTION_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "criteria"
    / "v2"
    / "extraction-v2.json"
)
_EXTRACTION_GOLDENS_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "criteria"
    / "v2"
    / "extraction-goldens-v2.json"
)


def load_concepts_seed(path: Path | None = None) -> ConceptsSeedSpec:
    source = path or _CONCEPTS_SEED_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_concepts_seed(data)


def load_matcher_types(path: Path | None = None) -> MatcherTypesSpec:
    source = path or _MATCHER_TYPES_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_matcher_types(data)


def load_extraction_contract(path: Path | None = None) -> ExtractionContractSpec:
    source = path or _EXTRACTION_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_extraction_contract(data)


def load_extraction_goldens(
    path: Path | None = None,
) -> Mapping[str, ExtractionGolden]:
    """Load the published per-concept extraction goldens.

    Returns a mapping concept_key -> golden; malformed documents raise
    ``ExtractionGoldenInvalid`` (the gate fails closed).
    """
    source = path or _EXTRACTION_GOLDENS_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_extraction_goldens(data)
