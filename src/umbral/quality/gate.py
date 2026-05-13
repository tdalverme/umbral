"""Quality gate deterministico para publicaciones inmobiliarias."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from umbral.config import CABA_NEIGHBORHOODS
from umbral.models import RawListing
from umbral.quality.types import QualityResult


MIN_QUALITY_SCORE = 55

_SUSPICIOUS_TERMS = (
    "anticipo para reservar",
    "transferencia inmediata",
    "sin visitar",
    "oportunidad unica",
    "precio irrisorio",
)


def _has_valid_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _parse_amount(value) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"(\d[\d\.,]*)", text)
    if not match:
        return None
    normalized = match.group(1).replace(".", "").replace(",", ".")
    try:
        amount = float(normalized)
    except ValueError:
        return None
    return amount if amount > 0 else None


def _parse_int(value) -> int | None:
    try:
        number = int(float(str(value or "").replace(",", ".").strip()))
    except ValueError:
        return None
    return number if number > 0 else None


def _feature_count(listing: RawListing) -> int:
    return sum(1 for value in listing.features.model_dump().values() if bool(value))


def evaluate_listing_quality(
    listing: RawListing,
    *,
    duplicate: bool = False,
    min_score: int = MIN_QUALITY_SCORE,
) -> QualityResult:
    """Evalua si una publicacion merece entrar al pipeline."""

    score = 100
    reasons: list[str] = []
    penalties: list[str] = []
    tags: list[str] = ["quality_gate"]

    if duplicate:
        return QualityResult(
            accepted=False,
            score=0,
            reasons=["Publicacion duplicada por hash/source/external_id"],
            tags=tags + ["duplicate"],
        )

    if not _has_valid_url(listing.url):
        score -= 40
        penalties.append("URL invalida o ausente")
        tags.append("missing_url")
    else:
        reasons.append("URL valida")

    amount = _parse_amount(listing.price)
    if amount is None:
        score -= 35
        penalties.append("Precio ausente o invalido")
        tags.append("missing_price")
    else:
        reasons.append("Precio presente")

    if str(listing.currency or "").upper() not in {"USD", "ARS"}:
        score -= 20
        penalties.append("Moneda ausente o no soportada")
        tags.append("invalid_currency")
    else:
        reasons.append("Moneda valida")

    neighborhood = str(listing.neighborhood or "").strip()
    if not neighborhood:
        score -= 30
        penalties.append("Barrio ausente")
        tags.append("missing_neighborhood")
    elif neighborhood not in CABA_NEIGHBORHOODS:
        score -= 8
        penalties.append("Barrio no reconocido en CABA")
        tags.append("unknown_neighborhood")
    else:
        reasons.append("Barrio reconocido")

    title = str(listing.title or "").strip()
    description = str(listing.description or "").strip()
    if len(title) < 12:
        score -= 10
        penalties.append("Titulo poco informativo")
    else:
        reasons.append("Titulo informativo")
    if len(description) < 120:
        score -= 18
        penalties.append("Descripcion pobre")
        tags.append("thin_description")
    else:
        reasons.append("Descripcion suficiente")

    rooms = _parse_int(listing.rooms)
    if rooms is None:
        score -= 10
        penalties.append("Ambientes ausentes o invalidos")
    elif rooms > 10:
        score -= 8
        penalties.append("Ambientes fuera de rango esperado")
    else:
        reasons.append("Ambientes coherentes")

    size = _parse_amount(listing.size_covered) or _parse_amount(listing.size_total)
    if size is not None and (size < 12 or size > 1000):
        score -= 8
        penalties.append("Superficie fuera de rango esperado")
    elif size is not None:
        reasons.append("Superficie presente")

    lower_text = f"{title}\n{description}".lower()
    suspicious = [term for term in _SUSPICIOUS_TERMS if term in lower_text]
    if suspicious:
        score -= min(30, 12 * len(suspicious))
        penalties.append("Senales sospechosas: " + ", ".join(suspicious[:3]))
        tags.append("suspicious")

    if listing.images:
        score += 4
        reasons.append("Tiene imagenes")
    if _feature_count(listing) >= 2:
        score += 4
        reasons.append("Tiene amenities/datos estructurados utiles")

    score = max(0, min(100, score))
    accepted = score >= max(0, min(100, min_score))
    if accepted:
        tags.append("accepted")
    else:
        tags.append("rejected")
    return QualityResult(
        accepted=accepted,
        score=score,
        reasons=reasons,
        penalties=penalties,
        tags=tags,
    )
