"""Generador de analisis personalizado para top matches."""

from __future__ import annotations

import json
from dataclasses import dataclass

import structlog

from umbral.analysis.llm_providers import BaseLLMProvider, get_llm_provider
from umbral.models import UserPreferences

logger = structlog.get_logger()


PERSONALIZED_SYSTEM_PROMPT = "Responde solo JSON valido, breve y honesto."

PERSONALIZED_USER_PROMPT_TEMPLATE = """Explicale a una persona por que esta propiedad puede matchear.
Tono: espanol rioplatense, de vos, cercano y profesional. No inventes datos.
No uses frases genericas como "muy buen match" si no mencionas datos concretos.
Estructura mental: 1-2 razones conectadas a sus preferencias, 1 trade-off o dato incierto, 1 veredicto corto.
Devolve SOLO JSON con esta forma:
{{"why_match":"2 frases cortas","warnings":"1 trade-off o string vacio","conclusion":"veredicto corto"}}

USER:
- ideal: {ideal_description}
- must_haves: {must_haves}
- presupuesto: {budget}
- ambientes: {rooms}
- barrios: {neighborhoods}

PROPIEDAD:
- titulo: {title}
- barrio: {listing_neighborhood}
- precio: {price}
- ambientes: {listing_rooms}
- features: {features}
- descripcion: {description}
- score: {similarity}

SCORING:
- fortalezas/gaps: {scoring_context}
"""


@dataclass
class PersonalizedAnalysis:
    """Resultado estructurado de analisis personalizado."""

    why_match: str
    warnings: str
    conclusion: str


class PersonalizedMatchAnalyzer:
    """Analiza un listing en contexto de preferencias de un usuario."""

    def __init__(self, provider: BaseLLMProvider | None = None):
        self._provider: BaseLLMProvider = provider or get_llm_provider()

    def _build_user_context(self, preferences: UserPreferences) -> dict:
        hard = preferences.hard_filters
        soft = preferences.soft_preferences

        must_haves = []
        if hard.requires_balcony:
            must_haves.append("balcon")
        if hard.requires_parking:
            must_haves.append("cochera")
        if hard.requires_pets_allowed:
            must_haves.append("acepte mascotas")
        if hard.requires_furnished:
            must_haves.append("amoblado")

        if hard.min_rooms and hard.max_rooms:
            rooms = f"{hard.min_rooms}-{hard.max_rooms}"
        elif hard.min_rooms:
            rooms = f"{hard.min_rooms}+"
        elif hard.max_rooms:
            rooms = f"hasta {hard.max_rooms}"
        else:
            rooms = "cualquiera"

        budget = f"hasta USD {hard.max_price_usd}" if hard.max_price_usd is not None else "sin limite"
        neighborhoods = ", ".join(hard.neighborhoods[:8]) if hard.neighborhoods else "todos CABA"

        return {
            "ideal_description": " ".join((soft.ideal_description or "sin descripcion").split())[:450],
            "must_haves": ", ".join(must_haves) if must_haves else "ninguno",
            "budget": budget,
            "rooms": rooms,
            "neighborhoods": neighborhoods,
        }

    def _build_listing_context(self, listing_data: dict) -> dict:
        features = listing_data.get("features", {}) or {}
        if isinstance(features, str):
            try:
                features = json.loads(features)
            except json.JSONDecodeError:
                features = {}

        feature_items = [key for key, value in features.items() if value]
        currency = listing_data.get("currency", "USD")
        price_raw = listing_data.get("price")
        price = f"ARS {price_raw}" if currency == "ARS" and price_raw else f"USD {price_raw}"

        description = " ".join((listing_data.get("description", "") or "").split())[:450]
        scoring_context = self._build_scoring_context(listing_data)
        return {
            "title": (listing_data.get("title", "") or "")[:120],
            "listing_neighborhood": listing_data.get("neighborhood", ""),
            "price": price,
            "listing_rooms": listing_data.get("rooms", ""),
            "features": ", ".join(feature_items[:10]) if feature_items else "ninguna",
            "description": description,
            "scoring_context": scoring_context,
        }

    def _build_scoring_context(self, listing_data: dict) -> str:
        parts: list[str] = []
        for criterion in (listing_data.get("criteria") or [])[:5]:
            if not isinstance(criterion, dict):
                continue
            name = criterion.get("name", "Criterio")
            score = criterion.get("score", "?")
            reason = criterion.get("reason", "")
            parts.append(f"{name}: {score} - {reason}")
        gaps = listing_data.get("gaps") or []
        if gaps:
            parts.append("A revisar: " + "; ".join(str(gap) for gap in gaps[:3]))
        return " | ".join(parts) if parts else "sin scoring explicable disponible"

    def _fallback(self) -> PersonalizedAnalysis:
        return PersonalizedAnalysis(
            why_match="Tiene buena afinidad con lo que buscas.",
            warnings="",
            conclusion="Vale la pena abrir la publicacion y validar los detalles clave.",
        )

    async def generate(
        self,
        preferences: UserPreferences,
        listing_data: dict,
        similarity_score: float,
    ) -> PersonalizedAnalysis:
        """Genera un analisis estructurado para notificacion."""
        try:
            user_context = self._build_user_context(preferences)
            listing_context = self._build_listing_context(listing_data)
            user_prompt = PERSONALIZED_USER_PROMPT_TEMPLATE.format(
                ideal_description=user_context["ideal_description"],
                must_haves=user_context["must_haves"],
                budget=user_context["budget"],
                rooms=user_context["rooms"],
                neighborhoods=user_context["neighborhoods"],
                title=listing_context["title"],
                listing_neighborhood=listing_context["listing_neighborhood"],
                price=listing_context["price"],
                listing_rooms=listing_context["listing_rooms"],
                features=listing_context["features"],
                description=listing_context["description"],
                similarity=f"{similarity_score:.2f}",
                scoring_context=listing_context["scoring_context"],
            )

            response = await self._provider.generate(
                system_prompt=PERSONALIZED_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=160,
            )

            text = (response.text or "").strip()
            if text.startswith("```"):
                parts = text.split("```")
                if len(parts) >= 2:
                    text = parts[1].strip()
                    if text.startswith("json"):
                        text = text[4:].strip()

            if not text:
                return self._fallback()

            data = json.loads(text)
            why_match = str(data.get("why_match", "")).strip()
            warnings = str(data.get("warnings", "")).strip()
            conclusion = str(data.get("conclusion", "")).strip()

            return PersonalizedAnalysis(
                why_match=(why_match or "Esta alineada con varias de tus prioridades principales.")[:420],
                warnings=warnings[:220],
                conclusion=(conclusion or "Vale revisarla en detalle para validar encaje final.")[:200],
            )

        except Exception as e:
            logger.warning("Error generando analisis personalizado", error=str(e))
            return self._fallback()
