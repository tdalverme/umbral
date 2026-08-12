"""Manual MercadoLibre rental import generator (intermediate source).

Two subcommands:
  auth   - prints the OAuth authorization URL, exchanges the pasted
           redirect URL for tokens, and stores them under .data/.
  fetch  - pages the official /sites/MLA/search API (rental category),
           maps items to import-contract records, validates them against
           contracts/import/v1/import-contract.json and writes the JSON
           batch for POST /imports/batches.

Credentials come from the environment (ML_CLIENT_ID, ML_CLIENT_SECRET,
ML_REDIRECT_URI), never from the repository.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from umbral.application.ingestion.import_contract import (
    parse_contract,
    validate_record,
)

_API_BASE = "https://api.mercadolibre.com"
_AUTH_BASE = "https://auth.mercadolibre.com.ar/authorization"
_RENTAL_CATEGORY = "MLA1459"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_TOKEN_PATH = _REPO_ROOT / ".data" / "ml-token.json"
_CONTRACT_PATH = _REPO_ROOT / "contracts" / "import" / "v1" / "import-contract.json"

_PROPERTY_TYPES = {
    "apartamento": "apartment",
    "departamento": "apartment",
    "depto": "apartment",
    "ph": "house",
    "casa": "house",
    "habitacion": "room",
    "habitación": "room",
    "monoambiente": "studio",
    "mono ambiente": "studio",
    "oficina": "commercial",
    "local": "commercial",
}


class MlImportError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class FetchResult:
    records: list[dict[str, object]]
    skipped: int
    invalid: int
    total_pages: int


def _env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise MlImportError(
            f"{name} is not set; add it to .env.local and load it into the environment"
        )
    return value


def _load_contract() -> Any:
    with _CONTRACT_PATH.open("r", encoding="utf-8") as handle:
        return parse_contract(json.load(handle))


def _attribute(item: Mapping[str, Any], attr_id: str) -> Mapping[str, Any] | None:
    for raw in item.get("attributes") or []:
        if isinstance(raw, Mapping) and raw.get("id") == attr_id:
            return raw
    return None


def _attr_number(attr: Mapping[str, Any]) -> float | None:
    for value in attr.get("values") or []:
        if isinstance(value, Mapping):
            struct = value.get("struct")
            if isinstance(struct, Mapping) and isinstance(
                struct.get("number"), (int, float)
            ):
                return float(struct["number"])
    value_name = attr.get("value_name")
    if isinstance(value_name, str) and value_name.strip():
        match = re.search(r"-?\d+(?:[.,]\d+)?", value_name)
        if match:
            return float(match.group().replace(",", "."))
    return None


def _attr_text(attr: Mapping[str, Any]) -> str | None:
    value_name = attr.get("value_name")
    if isinstance(value_name, str) and value_name.strip():
        return value_name.strip()
    return None


def _property_type(item: Mapping[str, Any]) -> str:
    attr = _attribute(item, "PROPERTY_TYPE")
    value = _attr_text(attr) if attr else None
    if value:
        normalized = value.lower().strip()
        for key, mapped in _PROPERTY_TYPES.items():
            if key in normalized:
                return mapped
    return "other"


def _address_text(item: Mapping[str, Any]) -> str | None:
    address = item.get("address")
    if not isinstance(address, Mapping):
        return None
    line = address.get("address_line")
    if isinstance(line, str) and line.strip():
        return line.strip()
    parts = []
    for key in ("neighborhood", "city_name", "state_name"):
        value = address.get(key)
        if isinstance(value, Mapping):
            name = value.get("name")
            if isinstance(name, str) and name.strip():
                parts.append(name.strip())
        elif isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return ", ".join(parts) if parts else None


def _published_at(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).isoformat()
    except ValueError:
        return None


def map_item(item: Mapping[str, Any]) -> dict[str, object] | None:
    """Map one search item to an import-contract record; None when a required
    field cannot be derived."""
    external_id = item.get("id")
    if not isinstance(external_id, str) or not external_id:
        return None
    price = item.get("price")
    if not isinstance(price, (int, float)):
        return None
    currency = item.get("currency_id")
    if currency not in {"ARS", "USD"}:
        return None
    address_text = _address_text(item)
    if not address_text:
        return None

    record: dict[str, object] = {
        "external_id": external_id,
        "operation": "rental",
        "property_type": _property_type(item),
        "price": float(price),
        "currency": currency,
        "address_text": address_text,
    }

    neighborhood = None
    address = item.get("address")
    if isinstance(address, Mapping):
        raw = address.get("neighborhood")
        if isinstance(raw, Mapping) and isinstance(raw.get("name"), str):
            neighborhood = raw["name"].strip()
    if neighborhood:
        record["neighborhood"] = neighborhood

    location = item.get("location")
    if isinstance(location, Mapping):
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            record["latitude"] = float(latitude)
            record["longitude"] = float(longitude)

    covered = _attribute(item, "COVERED_AREA")
    total = _attribute(item, "TOTAL_AREA")
    surface = _attr_number(covered) if covered else None
    if surface is None and total:
        surface = _attr_number(total)
    if surface is not None:
        record["surface_m2"] = surface

    rooms_attr = _attribute(item, "ROOMS") or _attribute(item, "AMBIENTES")
    rooms = _attr_number(rooms_attr) if rooms_attr else None
    if rooms is not None:
        record["rooms"] = int(rooms)

    beds_attr = _attribute(item, "BEDROOMS") or _attribute(item, "DORMITORIOS")
    beds = _attr_number(beds_attr) if beds_attr else None
    if beds is not None:
        record["bedrooms"] = int(beds)

    expenses_attr = _attribute(item, "EXPENSES")
    expenses = _attr_number(expenses_attr) if expenses_attr else None
    if expenses is not None:
        record["expenses"] = expenses

    permalink = item.get("permalink")
    if isinstance(permalink, str) and permalink.strip():
        record["url"] = permalink

    pictures = item.get("pictures")
    if isinstance(pictures, list):
        urls: list[str] = []
        for raw in pictures:
            if not isinstance(raw, Mapping):
                continue
            url = raw.get("secure_url") or raw.get("url")
            if isinstance(url, str) and url.startswith("https://"):
                urls.append(url)
        if urls:
            record["media_urls"] = urls[:50]

    published = _published_at(item.get("date_created"))
    if published:
        record["published_at"] = published

    return record


def _save_token(payload: Mapping[str, Any]) -> None:
    expires_at = int(time.time()) + int(payload.get("expires_in", 21600)) - 300
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(
        json.dumps(
            {
                "access_token": payload["access_token"],
                "refresh_token": payload.get("refresh_token"),
                "expires_at": expires_at,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _load_token() -> Mapping[str, Any]:
    if not _TOKEN_PATH.exists():
        raise MlImportError(
            "no token stored; run `python -m umbral.ops.import_ml auth` first"
        )
    try:
        parsed = json.loads(_TOKEN_PATH.read_text(encoding="utf-8"))
        if not isinstance(parsed, Mapping):
            raise MlImportError("stored token is not a JSON object")
        return parsed
    except json.JSONDecodeError as error:
        raise MlImportError(f"stored token is corrupt: {error}") from error


def _access_token(client: httpx.Client) -> str:
    token = _load_token()
    if int(token.get("expires_at", 0)) > int(time.time()):
        return str(token["access_token"])
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise MlImportError("token expired and no refresh token; run auth again")
    response = client.post(
        f"{_API_BASE}/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": _env("ML_CLIENT_ID"),
            "client_secret": _env("ML_CLIENT_SECRET"),
            "refresh_token": str(refresh_token),
        },
    )
    if response.status_code != 200:
        raise MlImportError(
            f"token refresh failed ({response.status_code}): "
            f"{response.text[:200]}"
        )
    payload = response.json()
    _save_token(payload)
    return str(payload["access_token"])


def command_auth() -> int:
    client_id = _env("ML_CLIENT_ID")
    redirect_uri = _env("ML_REDIRECT_URI")
    params = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "read offline_access",
        }
    )
    print("1. Open this URL in your browser and authorize with your account:")
    print(f"{_AUTH_BASE}?{params}")
    print("2. Paste the full redirect URL (it contains ?code=...):")
    redirect = input().strip()
    parsed = urlparse(redirect)
    code = parse_qs(parsed.query).get("code", [None])[0]
    if not code:
        raise MlImportError("no code= parameter found in the pasted URL")
    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"{_API_BASE}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": _env("ML_CLIENT_SECRET"),
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
    if response.status_code != 200:
        raise MlImportError(
            f"token exchange failed ({response.status_code}): "
            f"{response.text[:200]}"
        )
    _save_token(response.json())
    print(f"token stored at {_TOKEN_PATH}")
    return 0


def fetch(
    client: httpx.Client,
    *,
    query: str | None,
    max_items: int,
) -> FetchResult:
    contract = _load_contract()
    access_token = _access_token(client)
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    skipped = 0
    invalid = 0
    offset = 0
    pages = 0
    while offset < max_items:
        params: dict[str, Any] = {
            "category": _RENTAL_CATEGORY,
            "status": "active",
            "limit": min(50, max_items - offset),
            "offset": offset,
        }
        if query:
            params["q"] = query
        response = client.get(
            f"{_API_BASE}/sites/MLA/search",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code != 200:
            raise MlImportError(
                f"search failed ({response.status_code}): {response.text[:200]}"
            )
        body = response.json()
        items = body.get("results") or []
        if not items:
            break
        for raw in items:
            if not isinstance(raw, Mapping):
                continue
            external_id = raw.get("id")
            if not isinstance(external_id, str) or external_id in seen:
                continue
            seen.add(external_id)
            mapped = map_item(raw)
            if mapped is None:
                skipped += 1
                continue
            result = validate_record(mapped, contract)
            if not result.valid:
                invalid += 1
            records.append(mapped)
        total = body.get("paging", {}).get("total", 0)
        pages += 1
        if len(records) + skipped >= min(max_items, int(total or 0)):
            break
        offset += len(items)
        if len(items) < 50:
            break
    return FetchResult(
        records=records,
        skipped=skipped,
        invalid=invalid,
        total_pages=pages,
    )


def command_fetch(args: argparse.Namespace) -> int:
    query = args.query.strip() or None
    out_path = Path(args.out)
    with httpx.Client(timeout=30) as client:
        result = fetch(
            client,
            query=query,
            max_items=args.max_items,
        )
    envelope: dict[str, object] = {
        "contract_version": "1",
        "records": result.records,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(envelope, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"pages={result.total_pages} records={len(result.records)} "
        f"skipped={result.skipped} contract_invalid={result.invalid}"
    )
    print(f"batch written to {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="umbral.ops.import_ml",
        description="Manual MercadoLibre rental import generator.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("auth", help="authorize and store the OAuth token")
    fetch_parser = sub.add_parser("fetch", help="fetch and map rental listings")
    fetch_parser.add_argument("--q", dest="query", default="", help="free-text query")
    fetch_parser.add_argument(
        "--max-items",
        dest="max_items",
        type=int,
        default=100,
        help="maximum listings to fetch (default 100)",
    )
    fetch_parser.add_argument(
        "--out",
        default=str(_REPO_ROOT / ".data" / "ml-import.json"),
        help="output JSON batch path",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "auth":
        return command_auth()
    return command_fetch(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MlImportError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
