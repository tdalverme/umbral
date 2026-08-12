"""Manual ZonaProp rental import generator (intermediate source).

Fetch a ZonaProp search URL (the one you build in the browser with the
filters), parse the listing cards out of the HTML, map them to
import-contract records and write the JSON batch for POST /imports/batches.

Usage:
    python -m umbral.ops.import_zonaprop fetch \\
        --url "https://www.zonaprop.com.ar/departamentos-alquiler-palermo.html" \\
        --out .data/zonaprop-import.json --max-items 100

The URL must point to a rental listing ("alquiler" in the path); the
generator is a manual, low-volume companion, not a production crawler.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Sequence

import httpx

from umbral.application.ingestion.import_contract import (
    parse_contract,
    validate_record,
)

_BASE_URL = "https://www.zonaprop.com.ar"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT_PATH = _REPO_ROOT / "contracts" / "import" / "v1" / "import-contract.json"

_NUMBER_RE = re.compile(r"(\d[\d.]*)")


class ZonaPropError(Exception):
    pass


@dataclass(slots=True)
class Card:
    external_id: str
    url: str
    price_text: str = ""
    expenses_text: str = ""
    features: list[str] = field(default_factory=list)
    address_text: str = ""
    neighborhood_text: str = ""
    description: str = ""
    media_urls: list[str] = field(default_factory=list)


class _CardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[Card] = []
        self._current: Card | None = None
        self._div_depth = 0
        self._captures: list[tuple[str, str, list[str]]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        data_qa = attributes.get("data-qa") or ""
        if tag == "div" and data_qa.startswith("posting PROPERTY"):
            external_id = attributes.get("data-id", "")
            target = attributes.get("data-to-posting", "")
            if external_id and target:
                self._current = Card(
                    external_id=external_id,
                    url=f"{_BASE_URL}{target.split('?')[0]}",
                )
                self._div_depth = 1
            return
        if self._current is None:
            return
        if tag == "div":
            self._div_depth += 1
        if tag in {"h2", "h3", "h4"}:
            classes = attributes.get("class", "")
            if data_qa == "POSTING_CARD_PRICE":
                self._captures.append(("price", tag, []))
            elif data_qa == "expensas":
                self._captures.append(("expenses", tag, []))
            elif data_qa == "POSTING_CARD_FEATURES":
                self._captures.append(("features", tag, []))
            elif data_qa == "POSTING_CARD_LOCATION":
                self._captures.append(("location", tag, []))
            elif "location-address" in data_qa or "location-address" in (classes or ""):
                self._captures.append(("address", tag, []))
            elif data_qa == "POSTING_CARD_DESCRIPTION":
                self._captures.append(("description", tag, []))
        elif (
            tag == "span"
            and self._captures
            and self._captures[-1][0] == "features"
        ):
            self._captures.append(("feature", tag, []))
        elif tag == "img":
            src = attributes.get("src", "")
            if src and src.startswith("https://") and "cdn.com" in src:
                self._current.media_urls.append(src)

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "div":
            self._div_depth -= 1
            if self._div_depth > 0:
                return
            self.cards.append(self._current)
            self._current = None
            self._captures = []
            return
        if self._captures and self._captures[-1][1] == tag:
            kind, _, parts = self._captures.pop()
            text = self._join_text(parts)
            if kind == "price":
                self._current.price_text = text
            elif kind == "expenses":
                self._current.expenses_text = text
            elif kind == "location":
                self._current.neighborhood_text = text
            elif kind == "address":
                self._current.address_text = text
            elif kind == "description":
                self._current.description = text
            elif kind == "feature" and text:
                self._current.features.append(text)

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._captures:
            self._captures[-1][2].append(data)

    @staticmethod
    def _join_text(parts: Sequence[str]) -> str:
        text = html.unescape("".join(parts)).strip()
        return re.sub(r"\s+", " ", text)


def _extract_number(text: str) -> float | None:
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    return float(match.group(1).replace(".", ""))


def _parse_price(text: str) -> tuple[str | None, float | None]:
    if not text:
        return None, None
    if text.startswith("USD"):
        return "USD", _extract_number(text)
    return "ARS", _extract_number(text)


def _first_feature(features: Sequence[str], pattern: str) -> float | None:
    for feature in features:
        if re.search(pattern, feature):
            return _extract_number(feature)
    return None


def _property_type(url: str) -> str:
    lowered = url.lower()
    for token, mapped in [
        ("departamento", "apartment"),
        ("casa", "house"),
        ("ph", "house"),
        ("habitacion", "room"),
        ("monoambiente", "studio"),
        ("oficina", "commercial"),
        ("local", "commercial"),
    ]:
        if token in lowered:
            return mapped
    return "other"


def map_card(card: Card, search_url: str = "") -> dict[str, object] | None:
    currency, price = _parse_price(card.price_text)
    if not currency or price is None:
        return None
    record: dict[str, object] = {
        "external_id": f"zonaprop-{card.external_id}",
        "operation": "rental",
        "property_type": _property_type(card.url)
        if _property_type(card.url) != "other"
        else _property_type(search_url),
        "price": price,
        "currency": currency,
        "address_text": card.address_text or card.neighborhood_text,
    }
    expenses = _extract_number(card.expenses_text)
    if expenses is not None:
        record["expenses"] = expenses
    surface = _first_feature(card.features, r"m\s*[²2]")
    if surface is not None:
        record["surface_m2"] = surface
    rooms = _first_feature(card.features, r"\bamb\.")
    if rooms is not None:
        record["rooms"] = int(rooms)
    bedrooms = _first_feature(card.features, r"\bdorm\.")
    if bedrooms is not None:
        record["bedrooms"] = int(bedrooms)
    if card.neighborhood_text:
        record["neighborhood"] = card.neighborhood_text.split(",")[0].strip()
    if card.description:
        record["description"] = card.description[:20000]
    if card.media_urls:
        record["media_urls"] = card.media_urls[:50]
    record["url"] = card.url
    return record


def fetch(
    client: httpx.Client,
    *,
    url: str,
    max_items: int,
) -> tuple[list[dict[str, object]], int, int]:
    if "alquiler" not in url.lower():
        raise ZonaPropError(
            "the URL must be a rental search (path contains 'alquiler')"
        )
    contract = _load_contract()
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    skipped = 0
    invalid = 0
    page = 1
    while len(records) + skipped < max_items:
        page_url = f"{url}?pag={page}" if page > 1 else url
        response = client.get(
            page_url,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept-Language": "es-AR,es;q=0.9",
            },
        )
        if response.status_code != 200:
            raise ZonaPropError(
                f"zonaprop returned HTTP {response.status_code} for {page_url}"
            )
        parser = _CardParser()
        parser.feed(response.text)
        if not parser.cards:
            break
        for card in parser.cards:
            if card.external_id in seen:
                continue
            seen.add(card.external_id)
            mapped = map_card(card, search_url=url)
            if mapped is None:
                skipped += 1
                continue
            result = validate_record(mapped, contract)
            if not result.valid:
                invalid += 1
            records.append(mapped)
        if len(parser.cards) < 20:
            break
        page += 1
    return records, skipped, invalid


def _load_contract() -> Any:
    with _CONTRACT_PATH.open("r", encoding="utf-8") as handle:
        return parse_contract(json.load(handle))


def command_fetch(args: argparse.Namespace) -> int:
    out_path = Path(args.out)
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        records, skipped, invalid = fetch(
            client, url=args.url, max_items=args.max_items
        )
    envelope: dict[str, object] = {"contract_version": "1", "records": records}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(envelope, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"records={len(records)} skipped={skipped} contract_invalid={invalid}"
    )
    print(f"batch written to {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="umbral.ops.import_zonaprop",
        description="Manual ZonaProp rental import generator.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    fetch_parser = sub.add_parser("fetch", help="fetch and map a rental search")
    fetch_parser.add_argument("--url", required=True, help="ZonaProp search URL")
    fetch_parser.add_argument(
        "--max-items",
        dest="max_items",
        type=int,
        default=100,
        help="maximum listings to fetch (default 100)",
    )
    fetch_parser.add_argument(
        "--out",
        default=str(_REPO_ROOT / ".data" / "zonaprop-import.json"),
        help="output JSON batch path",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return command_fetch(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ZonaPropError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
