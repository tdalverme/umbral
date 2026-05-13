"""Scoring deterministico y explicable para usuario-propiedad."""

from __future__ import annotations

import json
import math
from typing import Any

from umbral.analysis import EmbeddingGenerator
from umbral.config import get_settings
from umbral.models import HardFilters, UserPreferences
from umbral.scoring.types import CriterionScore, ScoringResult


SCORING_VERSION = "1.0"
BUDGET_HARD_REJECT_MULTIPLIER = 1.15


def _clamp(value: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(round(value))))


def _as_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        text = str(value).strip()
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            text = text.replace(",", ".")
        return float(text)
    except (TypeError, ValueError):
        return default


def _as_int(value, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _jsonish(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _feature_dict(listing: dict) -> dict:
    raw_features = listing.get("raw_features")
    if raw_features is None and isinstance(listing.get("raw_listings"), dict):
        raw_features = listing["raw_listings"].get("features")
    if raw_features is None:
        raw_features = listing.get("features", {})
    return _jsonish(raw_features, {}) or {}


def _scores_dict(listing: dict) -> dict:
    return _jsonish(listing.get("scores"), {}) or {}


def _vector(value) -> list[float] | None:
    parsed = _jsonish(value, None)
    if not isinstance(parsed, list):
        return None
    out: list[float] = []
    for item in parsed:
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            return None
    return out


class ScoringEngine:
    """Combina reglas de negocio, senales IA y embeddings en un score explicable."""

    def __init__(self, exchange_rate: float | None = None):
        self.settings = None if exchange_rate is not None else get_settings()
        self.exchange_rate = exchange_rate or self.settings.ars_to_usd_rate

    def score(
        self,
        listing: dict,
        preferences: UserPreferences,
        *,
        preference_vector: list[float] | None = None,
        feedback_examples: list[dict] | None = None,
    ) -> ScoringResult:
        hard_result = self._hard_filters(listing, preferences.hard_filters)
        if hard_result:
            return hard_result

        criteria = [
            self._listing_quality(listing),
            self._price_budget_fit(listing, preferences),
            self._location_fit(listing, preferences),
            self._property_fit(listing, preferences),
            self._lifestyle_fit(listing, preferences),
            self._semantic_fit(listing, preference_vector),
            self._feedback_adjustment(feedback_examples or [], listing, preferences),
        ]
        weighted = sum(c.score * c.weight for c in criteria if c.weight > 0)
        total_weight = sum(c.weight for c in criteria if c.weight > 0) or 1
        final_score = _clamp(weighted / total_weight)
        band = self._band(final_score)
        gaps = self._gaps(listing, preferences, criteria)
        summary = self._summary(final_score, criteria, gaps)
        return ScoringResult(
            final_score=final_score,
            band=band,
            summary=summary,
            criteria=criteria,
            gaps=gaps,
            eligible=True,
        )

    def _hard_filters(self, listing: dict, hard: HardFilters) -> ScoringResult | None:
        gaps: list[str] = []
        if hard.operation_type:
            operation = listing.get("operation_type")
            if not operation and isinstance(listing.get("raw_listings"), dict):
                operation = listing["raw_listings"].get("operation_type")
            if operation and operation != hard.operation_type:
                gaps.append(f"Operacion {operation}, buscabas {hard.operation_type}.")

        price_usd = _as_float(listing.get("price_usd"))
        if hard.min_price_usd is not None and price_usd < hard.min_price_usd:
            gaps.append("Precio por debajo del minimo configurado.")
        if (
            hard.max_price_usd is not None
            and price_usd > hard.max_price_usd * BUDGET_HARD_REJECT_MULTIPLIER
        ):
            gaps.append("Precio supera tu presupuesto maximo.")

        neighborhood = str(listing.get("neighborhood") or "")
        if hard.neighborhoods and neighborhood not in hard.neighborhoods:
            gaps.append(f"Barrio {neighborhood or 'sin barrio'} fuera de tus barrios elegidos.")

        rooms = _as_int(listing.get("rooms"))
        if hard.min_rooms is not None and rooms < hard.min_rooms:
            gaps.append("Tiene menos ambientes que tu minimo.")
        if hard.max_rooms is not None and rooms > hard.max_rooms:
            gaps.append("Tiene mas ambientes que tu maximo.")

        features = _feature_dict(listing)
        if hard.requires_balcony and not features.get("has_balcony"):
            gaps.append("No se confirma balcon.")
        if hard.requires_pets_allowed and not features.get("is_pet_friendly"):
            gaps.append("No se confirma apto mascotas.")
        if hard.requires_furnished and not features.get("is_furnished"):
            gaps.append("No se confirma amoblado.")
        parking = listing.get("parking_spaces")
        if parking is None and isinstance(listing.get("raw_listings"), dict):
            parking = listing["raw_listings"].get("parking_spaces")
        if hard.requires_parking and not parking:
            gaps.append("No se confirma cochera.")

        if not gaps:
            return None
        return ScoringResult(
            final_score=0,
            band="ineligible",
            summary="La propiedad no cumple tus filtros excluyentes.",
            criteria=[
                CriterionScore(
                    name="Hard filters",
                    score=0,
                    weight=0,
                    reason="; ".join(gaps),
                )
            ],
            gaps=gaps,
            eligible=False,
        )

    def _listing_quality(self, listing: dict) -> CriterionScore:
        score = int(listing.get("quality_score") or listing.get("listing_quality_score") or 70)
        reason = "Calidad de publicacion suficiente para comparar."
        if score >= 85:
            reason = "Publicacion completa, confiable y con buen nivel de datos."
        elif score < 60:
            reason = "Publicacion incompleta o con baja confianza."
        return CriterionScore(name="Listing quality", score=_clamp(score), weight=12, reason=reason)

    def _price_budget_fit(self, listing: dict, preferences: UserPreferences) -> CriterionScore:
        hard = preferences.hard_filters
        price = _as_float(listing.get("price_usd"))
        if price <= 0:
            return CriterionScore(name="Price/budget fit", score=45, weight=18, reason="No hay precio USD confiable.")
        if hard.max_price_usd:
            ratio = price / hard.max_price_usd
            if ratio <= 0.75:
                return CriterionScore(name="Price/budget fit", score=92, weight=18, reason="Precio muy comodo contra tu presupuesto.")
            if ratio <= 0.95:
                return CriterionScore(name="Price/budget fit", score=82, weight=18, reason="Precio dentro de presupuesto con margen razonable.")
            if ratio <= 1:
                return CriterionScore(name="Price/budget fit", score=68, weight=18, reason="Precio dentro de presupuesto pero cerca del limite.")
            return CriterionScore(name="Price/budget fit", score=52, weight=18, reason="Precio levemente sobre tu presupuesto configurado.")
        ppm2 = _as_float(listing.get("price_per_m2_usd"))
        if ppm2 > 0:
            return CriterionScore(name="Price/budget fit", score=72, weight=18, reason="Tiene precio por m2 disponible para comparacion.")
        return CriterionScore(name="Price/budget fit", score=65, weight=18, reason="Sin presupuesto maximo, el precio pesa de forma neutral.")

    def _location_fit(self, listing: dict, preferences: UserPreferences) -> CriterionScore:
        neighborhood = str(listing.get("neighborhood") or "")
        chosen = preferences.hard_filters.neighborhoods
        scores = _scores_dict(listing)
        connectivity = float(scores.get("connectivity", 0.5) or 0.5)
        if chosen and neighborhood in chosen:
            base = 88
            reason = f"Esta en {neighborhood}, uno de tus barrios elegidos."
        elif not chosen:
            base = 70
            reason = "No restringiste barrios; se prioriza conectividad."
        else:
            base = 55
            reason = f"{neighborhood or 'Barrio desconocido'} no esta entre tus barrios preferidos."
        score = _clamp(base + (connectivity - 0.5) * 20)
        return CriterionScore(name="Location fit", score=score, weight=18, reason=reason)

    def _property_fit(self, listing: dict, preferences: UserPreferences) -> CriterionScore:
        hard = preferences.hard_filters
        features = _feature_dict(listing)
        score = 68
        reasons: list[str] = []
        rooms = _as_int(listing.get("rooms"))
        if hard.min_rooms and rooms >= hard.min_rooms:
            score += 8
            reasons.append("ambientes alineados")
        if hard.max_rooms and rooms <= hard.max_rooms:
            score += 5
        if hard.requires_balcony and features.get("has_balcony"):
            score += 8
            reasons.append("tiene balcon")
        if hard.requires_pets_allowed and features.get("is_pet_friendly"):
            score += 7
            reasons.append("acepta mascotas")
        if hard.requires_furnished and features.get("is_furnished"):
            score += 7
            reasons.append("amoblado confirmado")
        if hard.requires_parking:
            parking = listing.get("parking_spaces")
            if parking is None and isinstance(listing.get("raw_listings"), dict):
                parking = listing["raw_listings"].get("parking_spaces")
            if parking:
                score += 7
                reasons.append("cochera confirmada")
        if not reasons:
            reasons.append("caracteristicas fisicas razonables, sin grandes diferenciales.")
        return CriterionScore(name="Property fit", score=_clamp(score), weight=16, reason=", ".join(reasons).capitalize() + ".")

    def _lifestyle_fit(self, listing: dict, preferences: UserPreferences) -> CriterionScore:
        scores = _scores_dict(listing)
        soft = preferences.soft_preferences
        weighted_pairs = [
            ("quietness", soft.weight_quietness, "silencio"),
            ("luminosity", soft.weight_luminosity, "luminosidad"),
            ("connectivity", soft.weight_connectivity, "conectividad"),
            ("wfh_suitability", soft.weight_wfh_suitability, "home office"),
            ("modernity", soft.weight_modernity, "modernidad"),
            ("green_spaces", soft.weight_green_spaces, "espacios verdes"),
        ]
        total_weight = sum(max(weight, 0.1) for _, weight, _ in weighted_pairs)
        raw = sum(float(scores.get(key, 0.5) or 0.5) * max(weight, 0.1) for key, weight, _ in weighted_pairs)
        score = _clamp((raw / total_weight) * 100)
        strongest = sorted(
            weighted_pairs,
            key=lambda item: float(scores.get(item[0], 0.5) or 0.5) * item[1],
            reverse=True,
        )[:2]
        reason = "Mejor alineacion en " + " y ".join(label for _, _, label in strongest) + "."
        return CriterionScore(name="Lifestyle fit", score=score, weight=24, reason=reason)

    def _semantic_fit(self, listing: dict, preference_vector: list[float] | None) -> CriterionScore:
        if not preference_vector:
            return CriterionScore(name="Semantic/vibe fit", score=55, weight=10, reason="Sin vector de preferencias; score semantico neutral.")
        listing_vector = _vector(listing.get("vibe_embedding")) or _vector(listing.get("embedding_vector"))
        if not listing_vector:
            return CriterionScore(name="Semantic/vibe fit", score=55, weight=10, reason="Sin embedding del inmueble; score semantico neutral.")
        try:
            similarity = EmbeddingGenerator.cosine_similarity(preference_vector, listing_vector)
            score = _clamp(((similarity + 1) / 2) * 100)
        except (ValueError, TypeError, ZeroDivisionError):
            return CriterionScore(name="Semantic/vibe fit", score=55, weight=10, reason="No se pudo calcular similitud semantica.")
        return CriterionScore(name="Semantic/vibe fit", score=score, weight=10, reason="Similitud entre tu descripcion ideal y el vibe del inmueble.")

    def _feedback_adjustment(
        self,
        feedback_examples: list[dict],
        listing: dict,
        preferences: UserPreferences,
    ) -> CriterionScore:
        preference_feedback = [
            item for item in feedback_examples if item.get("reason") != "already_seen"
        ]
        likes = sum(1 for item in preference_feedback if item.get("feedback_type") == "like")
        dislikes = sum(1 for item in preference_feedback if item.get("feedback_type") == "dislike")
        if likes == dislikes == 0:
            return CriterionScore(name="Feedback adjustment", score=60, weight=2, reason="Aun no hay suficiente feedback historico.")
        score = _clamp(60 + likes * 5 - dislikes * 7)
        reasons = ["Ajuste liviano segun likes/dislikes previos"]
        reason_counts: dict[str, int] = {}
        for item in preference_feedback:
            reason = item.get("reason")
            if reason:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

        hard = preferences.hard_filters
        price = _as_float(listing.get("price_usd"))
        if reason_counts.get("too_expensive", 0) >= 2 and hard.max_price_usd and price > 0:
            if price / hard.max_price_usd >= 0.9:
                score -= 20
                reasons.append("sensibilidad reciente a precio cerca del limite")

        if reason_counts.get("bad_location", 0) >= 2 and hard.neighborhoods:
            neighborhood = str(listing.get("neighborhood") or "")
            if neighborhood not in hard.neighborhoods:
                score -= 12
                reasons.append("rechazos recientes por zona")

        rooms = _as_int(listing.get("rooms"))
        if reason_counts.get("too_small", 0) >= 2:
            if (hard.min_rooms and rooms <= hard.min_rooms) or not listing.get("price_per_m2_usd"):
                score -= 12
                reasons.append("rechazos recientes por tamano")

        features = _feature_dict(listing)
        if reason_counts.get("missing_key_feature", 0) >= 2:
            missing_required = (
                (hard.requires_balcony and not features.get("has_balcony"))
                or (hard.requires_pets_allowed and not features.get("is_pet_friendly"))
                or (hard.requires_furnished and not features.get("is_furnished"))
                or (hard.requires_parking and not listing.get("parking_spaces"))
            )
            if missing_required:
                score -= 15
                reasons.append("rechazos recientes por faltantes clave")

        scores = _scores_dict(listing)
        if reason_counts.get("style_condition", 0) >= 2:
            modernity = float(scores.get("modernity", 0.5) or 0.5)
            quality = int(listing.get("quality_score") or listing.get("listing_quality_score") or 70)
            if modernity < 0.6 or quality < 75:
                score -= 10
                reasons.append("rechazos recientes por estado o estilo")

        return CriterionScore(
            name="Feedback adjustment",
            score=_clamp(score),
            weight=2,
            reason=". ".join(reasons).capitalize() + ".",
        )

    def _gaps(self, listing: dict, preferences: UserPreferences, criteria: list[CriterionScore]) -> list[str]:
        gaps = [c.reason for c in criteria if c.score < 58]
        features = _feature_dict(listing)
        hard = preferences.hard_filters
        if hard.requires_pets_allowed and not features.get("is_pet_friendly"):
            gaps.append("No se pudo confirmar si acepta mascotas.")
        if not listing.get("price_per_m2_usd"):
            gaps.append("No hay precio por m2 confiable para evaluar oportunidad.")
        scores = _scores_dict(listing)
        if not scores:
            gaps.append("Faltan scores cualitativos del inmueble.")
        return list(dict.fromkeys(gaps))[:6]

    def _summary(self, final_score: int, criteria: list[CriterionScore], gaps: list[str]) -> str:
        best = sorted(criteria, key=lambda c: c.score, reverse=True)[:2]
        strengths = " y ".join(c.name.lower() for c in best)
        if final_score >= 85:
            return f"Match excelente por {strengths}."
        if final_score >= 75:
            return f"Muy buen match, especialmente por {strengths}."
        if final_score >= 65:
            return f"Match razonable con fortalezas en {strengths}, aunque conviene revisar gaps."
        return "Match debil; hay varios puntos que no alinean con tus preferencias."

    @staticmethod
    def _band(score: int) -> str:
        if score >= 85:
            return "excellent"
        if score >= 75:
            return "strong"
        if score >= 65:
            return "possible"
        if score >= 50:
            return "weak"
        return "poor"
