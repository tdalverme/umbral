"""Conformance of the published price table contract."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.agent_evals.price import load_price_table

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "contracts" / "agent-evals" / "v1" / "conversations-golden-v1.json"
RELEASES_PATH = ROOT / "contracts" / "agent-evals" / "v1" / "graph-releases-v1.json"
PRICE_PATH = ROOT / "contracts" / "agent-evals" / "v1" / "price-table-v1.json"


def test_price_table_matches_the_published_json() -> None:
    table = load_price_table(PRICE_PATH)
    assert table.registry_version == "price-table-v1"
    assert table.currency == "usd"
    assert table.entries


def test_price_table_covers_the_model_of_the_active_release() -> None:
    table = load_price_table(PRICE_PATH)
    from umbral.application.agent_evals.releases import load_releases

    releases = load_releases(RELEASES_PATH)
    active = releases.active_release()
    assert active is not None
    assert table.price_for(active.components.model_version) is not None


def test_price_table_document_is_valid_json() -> None:
    raw = json.loads(PRICE_PATH.read_text(encoding="utf-8"))
    assert raw["registry_version"] == "price-table-v1"
    assert isinstance(raw["prices"], list)
