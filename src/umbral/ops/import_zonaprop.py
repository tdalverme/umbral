"""Manual ZonaProp rental import generator (intermediate source).

Fetch a ZonaProp search URL (the one you build in the browser with the
filters), parse the listing cards out of the HTML, map them to
import-contract records and write the JSON batch for POST /imports/batches.

Usage:
    python -m umbral.ops.import_zonaprop fetch \\
        --url "https://www.zonaprop.com.ar/departamentos-alquiler-palermo.html" \\
        --out .data/zonaprop-import.json --max-items 100 --details

The URL must point to a rental listing ("alquiler" in the path); the
generator is a manual, low-volume companion, not a production crawler.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import math
import re
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
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
_CONTRACT_PATH = _REPO_ROOT / "contracts" / "import" / "v2" / "import-contract.json"

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


@dataclass(frozen=True, slots=True)
class Detail:
    title: str = ""
    latitude: float | None = None
    longitude: float | None = None
    surface_m2: float | None = None
    surface_covered_m2: float | None = None
    rooms: int | None = None
    bedrooms: int | None = None
    bathrooms: float | None = None
    toilettes: float | None = None
    parking_spaces: float | None = None
    age_years: float | None = None
    disposition: str | None = None
    orientation: str | None = None
    amenities: tuple[str, ...] = ()
    description: str = ""
    media_urls: tuple[str, ...] = ()


@dataclass(slots=True)
class _DetailCapture:
    kind: str
    tag: str
    depth: int
    parts: list[str] = field(default_factory=list)
    icon: str = ""


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


class _DetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._captures: list[_DetailCapture] = []
        self._scripts: list[str] = []
        self._feature_values: list[tuple[str, str]] = []
        self._general_features: list[str] = []
        self._title = ""
        self._meta_title = ""
        self._description = ""
        self._meta_description = ""
        self._media_urls: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if tag == "br":
            for capture in self._captures:
                if capture.kind == "description":
                    capture.parts.append("\n")
            return

        classes = set((attributes.get("class") or "").split())

        if tag == "meta":
            name = (attributes.get("name") or "").lower()
            property_name = (attributes.get("property") or "").lower()
            content = attributes.get("content") or ""
            if name == "description" or property_name == "og:description":
                self._meta_description = self._join_text([content])
            elif property_name == "og:title":
                self._meta_title = self._join_text([content])
            return

        if tag == "img":
            source = attributes.get("data-src") or attributes.get("src") or ""
            if (
                source.startswith("http")
                and "zonapropcdn.com/avisos/" in source
                and source not in self._media_urls
            ):
                self._media_urls.append(source.split("?", maxsplit=1)[0])
            return

        self._depth += 1

        if tag == "script":
            self._captures.append(
                _DetailCapture("script", tag, self._depth)
            )
        elif tag == "li" and "icon-feature" in classes:
            self._captures.append(
                _DetailCapture("main_feature", tag, self._depth)
            )
        elif tag == "span" and any(
            "description-text" in item for item in classes
        ):
            self._captures.append(
                _DetailCapture("general_feature", tag, self._depth)
            )
        elif tag == "div" and attributes.get("id") == "longDescription":
            self._captures.append(
                _DetailCapture("description", tag, self._depth)
            )
        elif tag == "h1" and "title-property" in classes:
            self._captures.append(_DetailCapture("title", tag, self._depth))
        elif tag == "i" and self._captures:
            capture = self._captures[-1]
            if capture.kind == "main_feature":
                capture.icon = next(
                    (
                        item
                        for item in classes
                        if item.startswith("icon-") and item != "icon-feature"
                    ),
                    "",
                )

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._captures) - 1, -1, -1):
            capture = self._captures[index]
            if capture.depth != self._depth or capture.tag != tag:
                continue
            self._captures.pop(index)
            self._finish_capture(capture)
            break
        self._depth = max(0, self._depth - 1)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in {"br", "img", "input", "link", "meta", "hr"}:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        for capture in self._captures:
            capture.parts.append(data)

    def detail(self) -> Detail:
        values: dict[str, str] = {}
        for script in self._scripts:
            for name in ("mapLatOf", "mapLngOf"):
                match = re.search(
                    rf"\b(?:const|let|var)\s+{name}\s*=\s*['\"]([^'\"]+)['\"]",
                    script,
                )
                if match and name not in values:
                    values[name] = match.group(1)

        latitude = _decode_coordinate(values.get("mapLatOf"), latitude=True)
        longitude = _decode_coordinate(values.get("mapLngOf"), latitude=False)
        surface_m2: float | None = None
        surface_covered_m2: float | None = None
        rooms: int | None = None
        bedrooms: int | None = None
        bathrooms: float | None = None
        toilettes: float | None = None
        parking_spaces: float | None = None
        age_years: float | None = None
        disposition: str | None = None
        orientation: str | None = None
        amenities: list[str] = []
        for icon, text in self._feature_values:
            number = _extract_number(text)
            if icon == "icon-stotal":
                surface_m2 = number
            elif icon == "icon-scubierta":
                surface_covered_m2 = number
            elif icon == "icon-ambiente" and number is not None:
                rooms = int(number)
            elif icon == "icon-dormitorio" and number is not None:
                bedrooms = int(number)
            elif icon == "icon-bano":
                bathrooms = number
            elif icon == "icon-toilete":
                toilettes = number
            elif icon == "icon-cochera":
                parking_spaces = number
            elif icon == "icon-antiguedad":
                age_years = number
            elif icon == "icon-disposicion":
                disposition = text or None
            elif icon == "icon-orientacion":
                orientation = text or None
            elif (
                icon in {"icon-luminosidad", "icon-seguridad", "icon-amoblado"}
                and text
            ):
                amenities.append(text)

        amenities.extend(self._general_features)
        return Detail(
            title=self._title or self._meta_title,
            latitude=latitude,
            longitude=longitude,
            surface_m2=surface_m2,
            surface_covered_m2=surface_covered_m2,
            rooms=rooms,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            toilettes=toilettes,
            parking_spaces=parking_spaces,
            age_years=age_years,
            disposition=disposition,
            orientation=orientation,
            amenities=_dedupe_texts(amenities),
            description=self._description or self._meta_description,
            media_urls=tuple(self._media_urls[:50]),
        )

    def _finish_capture(self, capture: _DetailCapture) -> None:
        text = self._join_text(capture.parts)
        if capture.kind != "description":
            text = re.sub(r"\s+", " ", text).strip()
        if capture.kind == "script":
            self._scripts.append("".join(capture.parts))
        elif capture.kind == "main_feature":
            self._feature_values.append((capture.icon, text))
        elif capture.kind == "general_feature" and text:
            self._general_features.append(text)
        elif capture.kind == "title":
            self._title = text
        elif capture.kind == "description":
            self._description = text

    @staticmethod
    def _join_text(parts: Sequence[str]) -> str:
        text = html.unescape("".join(parts)).strip()
        return re.sub(r"[ \t\r\f\v]+", " ", text)


def _dedupe_texts(values: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return tuple(result)


def _decode_coordinate(value: str | None, *, latitude: bool) -> float | None:
    if not value:
        return None
    try:
        decoded = base64.b64decode(value, validate=True).decode("ascii").strip()
        coordinate = float(decoded.replace(",", "."))
    except (ValueError, UnicodeDecodeError):
        return None
    if not math.isfinite(coordinate):
        return None
    if latitude and not -90 <= coordinate <= 90:
        return None
    if not latitude and not -180 <= coordinate <= 180:
        return None
    return coordinate


def parse_detail_html(source: str) -> Detail:
    parser = _DetailParser()
    parser.feed(source)
    parser.close()
    return parser.detail()


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


def map_card(
    card: Card,
    search_url: str = "",
    *,
    detail: Detail | None = None,
) -> dict[str, object] | None:
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
    if detail is not None:
        if detail.title:
            record["title"] = detail.title[:500]
        if detail.latitude is not None and detail.longitude is not None:
            record["latitude"] = detail.latitude
            record["longitude"] = detail.longitude
        if detail.surface_m2 is not None:
            record["surface_m2"] = detail.surface_m2
        if detail.surface_covered_m2 is not None:
            record["surface_covered_m2"] = detail.surface_covered_m2
        if detail.rooms is not None:
            record["rooms"] = detail.rooms
        if detail.bedrooms is not None:
            record["bedrooms"] = detail.bedrooms
        if detail.bathrooms is not None:
            record["bathrooms"] = detail.bathrooms
        if detail.toilettes is not None:
            record["toilettes"] = detail.toilettes
        if detail.parking_spaces is not None:
            record["parking_spaces"] = detail.parking_spaces
        if detail.age_years is not None:
            record["age_years"] = detail.age_years
        if detail.disposition is not None:
            record["disposition"] = detail.disposition
        if detail.orientation is not None:
            record["orientation"] = detail.orientation
        if detail.amenities:
            record["amenities"] = list(detail.amenities)
        if detail.description:
            record["description"] = detail.description[:20000]
        if detail.media_urls:
            record["media_urls"] = list(detail.media_urls[:50])
    record["url"] = card.url
    return record


def fetch(
    client: httpx.Client,
    *,
    url: str,
    max_items: int,
    detail_loader: Callable[[str], str] | None = None,
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
            detail = (
                parse_detail_html(detail_loader(card.url))
                if detail_loader is not None
                else None
            )
            mapped = map_card(card, search_url=url, detail=detail)
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


@contextmanager
def _playwright_detail_loader() -> Iterator[Callable[[str], str]]:
    try:
        from playwright.sync_api import (  # type: ignore[import-not-found]
            sync_playwright,
        )
    except ImportError as error:
        raise ZonaPropError(
            "detail mode requires the 'scraping' extra and Chromium"
        ) from error

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
        except Exception as error:
            raise ZonaPropError(
                "could not launch Chromium; install the Playwright browser"
            ) from error

        context = browser.new_context(
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
            user_agent=_USER_AGENT,
            extra_http_headers={
                "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
                "DNT": "1",
            },
        )
        page = context.new_page()

        def load(detail_url: str) -> str:
            try:
                response = page.goto(
                    detail_url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                if response is not None and response.status >= 400:
                    raise ZonaPropError(
                        "zonaprop detail returned HTTP "
                        f"{response.status} for {detail_url}"
                    )
                page.wait_for_timeout(1500)
                source = str(page.content())
            except ZonaPropError:
                raise
            except Exception as error:
                raise ZonaPropError(
                    f"could not load zonaprop detail {detail_url}"
                ) from error
            if "Just a moment..." in source or "cf-chl-" in source:
                raise ZonaPropError(
                    f"zonaprop challenge blocked detail page {detail_url}"
                )
            return source

        try:
            yield load
        finally:
            context.close()
            browser.close()


def _load_contract() -> Any:
    with _CONTRACT_PATH.open("r", encoding="utf-8") as handle:
        return parse_contract(json.load(handle))


def command_fetch(args: argparse.Namespace) -> int:
    out_path = Path(args.out)
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        if args.details:
            with _playwright_detail_loader() as detail_loader:
                records, skipped, invalid = fetch(
                    client,
                    url=args.url,
                    max_items=args.max_items,
                    detail_loader=detail_loader,
                )
        else:
            records, skipped, invalid = fetch(
                client, url=args.url, max_items=args.max_items
            )
    envelope: dict[str, object] = {"contract_version": "2", "records": records}
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
    fetch_parser.add_argument(
        "--details",
        action="store_true",
        help="open each detail page with Playwright and enrich the record",
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
