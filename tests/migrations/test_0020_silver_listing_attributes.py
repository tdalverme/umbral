"""Silver v2 listing attributes migration contract tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from umbral.infrastructure.db.migrations import expected_schema


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0020_silver_listing_attributes.py")
    spec = importlib.util.spec_from_file_location("silver_attributes_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_silver_attributes_revision_follows_current_head() -> None:
    revision = _revision_module()
    assert revision.revision == "0020_silver_listing_attributes"
    assert revision.down_revision == "0019_feedback_strength_confidence"


def test_silver_listing_declares_new_attribute_columns_and_checks() -> None:
    listings = expected_schema().tables["silver_listings"]
    for column in (
        "title_text",
        "surface_covered_m2",
        "bathrooms",
        "toilettes",
        "parking_spaces",
        "age_years",
        "disposition",
        "orientation",
        "media_urls",
    ):
        assert column in listings.c
    for constraint in (
        "ck_silver_listings_surface_covered",
        "ck_silver_listings_bathrooms",
        "ck_silver_listings_toilettes",
        "ck_silver_listings_parking_spaces",
        "ck_silver_listings_age_years",
    ):
        assert any(item.name == constraint for item in listings.constraints)
