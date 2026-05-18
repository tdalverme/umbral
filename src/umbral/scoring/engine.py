"""Scoring deterministico y explicable para usuario-propiedad."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from umbral.analysis import EmbeddingGenerator
from umbral.config import get_settings
from umbral.models import HardFilters, UserPreferences
from umbral.scoring.types import CriterionScore, ScoringResult
from umbral.urban import UrbanSignalCalculator

SCORING_VERSION = "2.0"
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
    """Combina reglas de negocio, senales IA, senales urbanas y feedback."""

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
        semantic_calibration: dict | None = None,
    ) -> ScoringResult:
        feedback_profile = self._feedback_profile(feedback_examples or [])
        hard_result = self._hard_filters(listing, preferences.hard_filters)
        if hard_result:
            return hard_result

        criteria = [
            self._cost_fit(listing, preferences, feedback_profile),
            self._property_fit(listing, preferences, feedback_profile),
            self._urban_fit(listing, preferences, feedback_profile),
            self._lifestyle_fit(listing, preferences),
            self._semantic_fit(listing, preference_vector, feedback_profile, semantic_calibration),
            self._market_value(listing),
            self._freshness_confidence(listing),
        ]
        weighted = sum(c.score * c.weight for c in criteria if c.weight > 0)
        total_weight = sum(c.weight for c in criteria if c.weight > 0) or 1
        final_score = _clamp(weighted / total_weight)
        band = self._band(final_score)
        gaps = self._gaps(listing, preferences, criteria)
        summary = self._summary(final_score, criteria)
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
        operation = listing.get("operation_type")
        if not operation and isinstance(listing.get("raw_listings"), dict):
            operation = listing["raw_listings"].get("operation_type")
        if hard.operation_type and operation and operation != hard.operation_type:
            gaps.append(f"Operacion {operation}, buscabas {hard.operation_type}.")

        budget_cost = self._budget_cost_usd(listing, hard.operation_type)
        if hard.min_price_usd is not None and budget_cost < hard.min_price_usd:
            gaps.append("Precio por debajo del minimo configurado.")
        if (
            hard.max_price_usd is not None
            and budget_cost > hard.max_price_usd * BUDGET_HARD_REJECT_MULTIPLIER
        ):
            gaps.append("Costo total supera tu presupuesto maximo.")

        neighborhood = str(listing.get("neighborhood") or "")
        if hard.neighborhoods and neighborhood not in hard.neighborhoods:
            gaps.append(f"Barrio {neighborhood or 'sin barrio'} fuera de tus barrios elegidos.")

        rooms = _as_int(listing.get("rooms"))
        if hard.min_rooms is not None and rooms < hard.min_rooms:
            gaps.append("Tiene menos ambientes que tu minimo.")
        if hard.max_rooms is not None and rooms > hard.max_rooms:
            gaps.append("Tiene mas ambientes que tu maximo.")

        size_m2 = self._size_m2(listing)
        if hard.min_size_m2 is not None and size_m2 > 0 and size_m2 < hard.min_size_m2:
            gaps.append("Superficie por debajo del minimo configurado.")

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
            criteria=[CriterionScore(name="Hard filters", score=0, weight=0, reason="; ".join(gaps))],
            gaps=gaps,
            eligible=False,
        )

    def _cost_fit(
        self,
        listing: dict,
        preferences: UserPreferences,
        feedback_profile: dict[str, float],
    ) -> CriterionScore:
        hard = preferences.hard_filters
        cost = self._budget_cost_usd(listing, hard.operation_type)
        if cost <= 0:
            return CriterionScore(name="Cost fit", score=45, weight=20, reason="No hay costo USD confiable.")
        if hard.max_price_usd:
            ratio = cost / hard.max_price_usd
            label = "costo total" if hard.operation_type == "alquiler" else "precio"
            if ratio <= 0.75:
                score, reason = 92, f"{label.capitalize()} muy comodo contra tu presupuesto."
            elif ratio <= 0.95:
                score, reason = 82, f"{label.capitalize()} dentro de presupuesto con margen razonable."
            elif ratio <= 1:
                score, reason = 68, f"{label.capitalize()} dentro de presupuesto pero cerca del limite."
            else:
                score, reason = 52, f"{label.capitalize()} levemente sobre tu presupuesto configurado."
            penalty = min(18, int(feedback_profile.get("price_sensitivity", 0) * 12))
            if penalty and ratio >= 0.9:
                score -= penalty
                reason += " Feedback reciente marca sensibilidad a precio."
            return CriterionScore(name="Cost fit", score=_clamp(score), weight=20, reason=reason)
        if _as_float(listing.get("price_per_m2_usd")) > 0:
            return CriterionScore(name="Cost fit", score=72, weight=20, reason="Tiene precio por m2 disponible para comparacion.")
        return CriterionScore(name="Cost fit", score=65, weight=20, reason="Sin presupuesto maximo, el costo pesa de forma neutral.")

    def _property_fit(
        self,
        listing: dict,
        preferences: UserPreferences,
        feedback_profile: dict[str, float],
    ) -> CriterionScore:
        hard = preferences.hard_filters
        features = _feature_dict(listing)
        score = 64
        reasons: list[str] = []
        rooms = _as_int(listing.get("rooms"))
        if hard.min_rooms and rooms >= hard.min_rooms:
            score += 7
            reasons.append("ambientes alineados")
        if hard.max_rooms and rooms <= hard.max_rooms:
            score += 4
        size_m2 = self._size_m2(listing)
        if hard.min_size_m2 and size_m2 >= hard.min_size_m2:
            score += 8
            reasons.append("superficie suficiente")
        elif size_m2 > 0:
            score += 3
            reasons.append("superficie informada")
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
        if feedback_profile.get("missing_feature_sensitivity"):
            score -= min(14, int(feedback_profile["missing_feature_sensitivity"] * 10))
            reasons.append("feedback reciente penaliza faltantes clave")
        if feedback_profile.get("size_sensitivity") and (
            not size_m2 or (hard.min_size_m2 and size_m2 <= hard.min_size_m2 * 1.1)
        ):
            score -= min(12, int(feedback_profile["size_sensitivity"] * 9))
            reasons.append("feedback reciente penaliza tamano")
        if not reasons:
            reasons.append("caracteristicas fisicas razonables, sin grandes diferenciales")
        return CriterionScore(name="Property fit", score=_clamp(score), weight=18, reason=", ".join(reasons).capitalize() + ".")

    def _urban_fit(
        self,
        listing: dict,
        preferences: UserPreferences,
        feedback_profile: dict[str, float],
    ) -> CriterionScore:
        signals = self._urban_signals(listing)
        if signals["confidence"] <= 0.25:
            return CriterionScore(name="Urban fit", score=50, weight=22, reason="Sin senales urbanas confiables; se usa score neutral.")

        soft = preferences.soft_preferences
        quiet_weight = max(soft.weight_quietness, 0.1)
        noise_penalty = signals["noise_risk"] * quiet_weight * (1 - soft.noise_tolerance)
        calm_bonus = signals["residential_calm"] * quiet_weight * (1 - min(0.8, soft.noise_tolerance))
        walkability = signals["walkability"] * max(soft.weight_walkability, 0.1)
        transit = signals["transit_access"] * max(soft.weight_connectivity, 0.1)
        green = signals["green_access"] * max(soft.weight_green_spaces, 0.1)
        urban_activity = (
            0.55 * signals["cafe_lifestyle"] + 0.45 * signals["commercial_intensity"]
        ) * max(soft.weight_urban_activity, 0.1)
        total = (
            max(soft.weight_walkability, 0.1)
            + max(soft.weight_connectivity, 0.1)
            + max(soft.weight_green_spaces, 0.1)
            + max(soft.weight_urban_activity, 0.1)
            + quiet_weight
        )
        score = ((walkability + transit + green + urban_activity + calm_bonus - noise_penalty) / total) * 100 + 20
        if feedback_profile.get("location_sensitivity"):
            score -= min(12, int(feedback_profile["location_sensitivity"] * 8))
        reason = (
            f"Caminabilidad {int(signals['walkability'] * 100)}, transporte {int(signals['transit_access'] * 100)} "
            f"y riesgo de ruido {int(signals['noise_risk'] * 100)}."
        )
        return CriterionScore(name="Urban fit", score=_clamp(score), weight=22, reason=reason)

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
        return CriterionScore(name="Lifestyle fit", score=score, weight=16, reason=reason)

    def _semantic_fit(
        self,
        listing: dict,
        preference_vector: list[float] | None,
        feedback_profile: dict[str, float],
        semantic_calibration: dict | None = None,
    ) -> CriterionScore:
        if not preference_vector:
            return CriterionScore(name="Semantic/vibe fit", score=55, weight=12, reason="Sin vector de preferencias; score semantico neutral.")
        if semantic_calibration:
            score = int(semantic_calibration["score"])
            metadata = dict(semantic_calibration.get("metadata") or {})
            if feedback_profile.get("style_sensitivity"):
                penalty = min(10, int(feedback_profile["style_sensitivity"] * 8))
                score -= penalty
                metadata["style_feedback_penalty"] = penalty
            calibration = metadata.get("calibration", "pool_percentile_v1")
            if calibration == "pool_percentile_v1":
                percentile = int(float(metadata.get("percentile", 0)) * 100)
                reason = f"Vibe calibrado contra el pool de candidatos; percentil {percentile}."
            elif calibration == "flat_distribution_v1":
                reason = "Vibe calibrado con cautela porque las similitudes del pool son muy parecidas."
            else:
                reason = "Vibe estimado por similitud absoluta por falta de candidatos comparables."
            return CriterionScore(
                name="Semantic/vibe fit",
                score=_clamp(score),
                weight=12,
                reason=reason,
                metadata=metadata,
            )
        listing_vector = _vector(listing.get("vibe_embedding")) or _vector(listing.get("embedding_vector"))
        if not listing_vector:
            return CriterionScore(name="Semantic/vibe fit", score=55, weight=12, reason="Sin embedding del inmueble; score semantico neutral.")
        try:
            similarity = EmbeddingGenerator.cosine_similarity(preference_vector, listing_vector)
            score = _clamp(((similarity + 1) / 2) * 100)
        except (ValueError, TypeError, ZeroDivisionError):
            return CriterionScore(name="Semantic/vibe fit", score=55, weight=12, reason="No se pudo calcular similitud semantica.")
        if feedback_profile.get("style_sensitivity"):
            score -= min(10, int(feedback_profile["style_sensitivity"] * 8))
        return CriterionScore(name="Semantic/vibe fit", score=_clamp(score), weight=12, reason="Similitud entre tu descripcion ideal y el vibe del inmueble.")

    def _market_value(self, listing: dict) -> CriterionScore:
        benchmark = listing.get("market_benchmark") or {}
        sample_count = _as_int(benchmark.get("sample_count") or listing.get("market_sample_count"))
        median = _as_float(benchmark.get("median_price_per_m2_usd") or listing.get("market_median_price_per_m2_usd"))
        ppm2 = _as_float(listing.get("price_per_m2_usd"))
        if sample_count < 10 or median <= 0 or ppm2 <= 0:
            return CriterionScore(name="Market value", score=65, weight=8, reason="Sin comparables suficientes para evaluar oportunidad.")
        ratio = ppm2 / median
        if ratio <= 0.9:
            score, reason = 88, "Precio por m2 mejor que comparables del barrio."
        elif ratio <= 1.05:
            score, reason = 72, "Precio por m2 alineado a comparables."
        elif ratio <= 1.2:
            score, reason = 55, "Precio por m2 algo alto contra comparables."
        else:
            score, reason = 42, "Precio por m2 muy alto contra comparables."
        return CriterionScore(name="Market value", score=score, weight=8, reason=reason)

    def _freshness_confidence(self, listing: dict) -> CriterionScore:
        quality = int(listing.get("quality_score") or listing.get("listing_quality_score") or 70)
        urban_confidence = self._urban_signals(listing)["confidence"]
        score = _clamp(35 + min(quality, 80) * 0.35 + urban_confidence * 15)
        reason = "Confianza suficiente para comparar."
        if quality < 55 or urban_confidence < 0.35:
            reason = "Baja confianza por publicacion incompleta o senales urbanas debiles."
        elif score >= 70:
            reason = "Datos suficientes y senales urbanas confiables."
        return CriterionScore(name="Freshness/confidence", score=score, weight=4, reason=reason)

    def _urban_signals(self, listing: dict) -> dict[str, Any]:
        raw = listing.get("urban_signals")
        if raw is None:
            joined = listing.get("listing_urban_signals")
            if isinstance(joined, list) and joined:
                raw = joined[0]
            elif isinstance(joined, dict):
                raw = joined
        raw = _jsonish(raw, {}) if isinstance(raw, str) else raw
        if isinstance(raw, dict) and isinstance(raw.get("signals"), dict):
            raw = raw["signals"]
        if not isinstance(raw, dict):
            return UrbanSignalCalculator().neutral().signals
        return {**UrbanSignalCalculator().neutral().signals, **raw}

    def _budget_cost_usd(self, listing: dict, operation_type: str | None) -> float:
        price = _as_float(listing.get("price_usd"))
        if operation_type == "venta":
            return price
        total = _as_float(listing.get("total_monthly_cost_usd"))
        if total > 0:
            return total
        maintenance = _as_float(listing.get("maintenance_fee_usd"))
        if maintenance <= 0:
            maintenance = self._maintenance_fee_usd(listing)
        return price + maintenance if price > 0 else 0.0

    def _maintenance_fee_usd(self, listing: dict) -> float:
        raw = listing.get("maintenance_fee")
        if raw is None and isinstance(listing.get("raw_listings"), dict):
            raw = listing["raw_listings"].get("maintenance_fee")
        if raw is None:
            return 0.0
        text = str(raw).lower()
        amount = _as_float(text)
        if amount <= 0:
            return 0.0
        if "usd" in text or "u$s" in text:
            return amount
        if amount > 500:
            return round(amount / self.exchange_rate, 2)
        return amount

    def _size_m2(self, listing: dict) -> float:
        for key in ("size_covered_m2", "size_total_m2", "size_covered", "size_total"):
            value = listing.get(key)
            if value is None and isinstance(listing.get("raw_listings"), dict):
                value = listing["raw_listings"].get(key)
            parsed = _as_float(value)
            if parsed > 0:
                return parsed
        return 0.0

    def _feedback_profile(self, feedback_examples: list[dict]) -> dict[str, float]:
        now = datetime.now(timezone.utc)
        signals = {
            "price_sensitivity": 0.0,
            "location_sensitivity": 0.0,
            "size_sensitivity": 0.0,
            "missing_feature_sensitivity": 0.0,
            "style_sensitivity": 0.0,
        }
        reason_map = {
            "too_expensive": "price_sensitivity",
            "bad_location": "location_sensitivity",
            "too_small": "size_sensitivity",
            "missing_key_feature": "missing_feature_sensitivity",
            "style_condition": "style_sensitivity",
        }
        for item in (feedback_examples or [])[:50]:
            if item.get("feedback_type") != "dislike":
                continue
            reason = item.get("reason")
            if reason == "already_seen" or reason not in reason_map:
                continue
            weight = 1.0
            created_at = item.get("created_at")
            if created_at:
                try:
                    parsed = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    age_days = max(0, (now - parsed).days)
                    weight = max(0.25, 1 - age_days / 90)
                except ValueError:
                    weight = 1.0
            signals[reason_map[reason]] += weight
        return {key: min(2.5, value) for key, value in signals.items()}

    def _price_budget_fit(self, listing: dict, preferences: UserPreferences) -> CriterionScore:
        return self._cost_fit(listing, preferences, self._feedback_profile([]))

    def _feedback_adjustment(
        self,
        feedback_examples: list[dict],
        listing: dict,
        preferences: UserPreferences,
    ) -> CriterionScore:
        profile = self._feedback_profile(feedback_examples)
        score = _clamp(60 - sum(profile.values()) * 5)
        return CriterionScore(name="Feedback profile", score=score, weight=0, reason="Feedback incorporado en criterios concretos.")

    def _gaps(self, listing: dict, preferences: UserPreferences, criteria: list[CriterionScore]) -> list[str]:
        gaps = [c.reason for c in criteria if c.score < 58 and c.weight > 0]
        features = _feature_dict(listing)
        hard = preferences.hard_filters
        if hard.requires_pets_allowed and not features.get("is_pet_friendly"):
            gaps.append("No se pudo confirmar si acepta mascotas.")
        if not listing.get("price_per_m2_usd"):
            gaps.append("No hay precio por m2 confiable para evaluar oportunidad.")
        if self._urban_signals(listing)["confidence"] <= 0.25:
            gaps.append("No hay senales urbanas confiables para esta ubicacion.")
        if not _scores_dict(listing):
            gaps.append("Faltan scores cualitativos del inmueble.")
        return list(dict.fromkeys(gaps))[:6]

    def _summary(self, final_score: int, criteria: list[CriterionScore]) -> str:
        best = sorted([c for c in criteria if c.weight > 0], key=lambda c: c.score, reverse=True)[:2]
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
