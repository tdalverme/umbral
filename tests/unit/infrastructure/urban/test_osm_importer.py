"""US4 T039: OSM tag classification against the contract tag mappings.

The classic osmium classification is a pure lookup; exercise it against small
fake tag dicts without needing a real planet file or the osmium binary.
"""

from __future__ import annotations

from umbral.application.urban.contract import TagMapping
from umbral.infrastructure.urban.osm_importer import (
    OsmiumUnavailable,
    _tags,
    classify,
)

_POI = [
    TagMapping(
        category="cafe",
        osm_tags=(("amenity", "cafe"),),
    ),
    TagMapping(
        category="supermarket",
        osm_tags=(("shop", "supermarket"),),
    ),
    TagMapping(
        category="nightlife",
        osm_tags=(("amenity", "bar"), ("amenity", "pub"), ("amenity", "nightclub")),
    ),
]

_LINEAR = [
    TagMapping(
        category="subway_line",
        osm_tags=(("railway", "subway"),),
    ),
    TagMapping(
        category="major_road",
        osm_tags=(("highway", "primary"), ("highway", "secondary")),
    ),
]


def test_classify_matches_a_single_tag_category() -> None:
    assert classify({"amenity": "cafe"}, _POI) == "cafe"


def test_classify_matches_any_tag_of_a_multi_tag_category() -> None:
    assert classify({"amenity": "bar"}, _POI) == "nightlife"
    assert classify({"amenity": "nightclub"}, _POI) == "nightlife"


def test_classify_returns_none_for_unmapped_tags() -> None:
    assert classify({"amenity": "restaurant"}, _POI) is None
    assert classify({"highway": "residential"}, _POI) is None


def test_classify_ignores_extra_tags() -> None:
    tags = {"amenity": "cafe", "name": "Café Rivadavia", "opening_hours": "8-20"}
    assert classify(tags, _POI) == "cafe"


def test_classify_applies_to_linear_mappings() -> None:
    assert classify({"railway": "subway"}, _LINEAR) == "subway_line"
    assert classify({"highway": "secondary"}, _LINEAR) == "major_road"
    assert classify({"highway": "service"}, _LINEAR) is None


def test_pyosmium_tag_list_is_converted_before_classification() -> None:
    tags = _tags((("amenity", "cafe"), ("name", "Cafe Central")))

    assert tags == {"amenity": "cafe", "name": "Cafe Central"}
    assert classify(tags, _POI) == "cafe"


def test_osmium_unavailable_is_a_runtime_error() -> None:
    assert issubclass(OsmiumUnavailable, RuntimeError)
