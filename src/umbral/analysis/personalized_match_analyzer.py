"""
Generador de análisis personalizado por usuario + propiedad.

Se ejecuta solo en etapa de matching para listings con alta similitud.
"""

import json
from dataclasses import dataclass
import structlog

from umbral.analysis.llm_providers import get_llm_provider, BaseLLMProvider
from umbral.models import UserPreferences

logger = structlog.get_logger()


PERSONALIZED_SYSTEM_PROMPT = (
    "Segui exactamente las instrucciones del prompt de usuario."
)

PERSONALIZED_USER_PROMPT_TEMPLATE = """Sos un asesor inmobiliario personal experto,  perspicaz y sumamente honesto que ayuda a buscar depto en CABA.
Escribís en español rioplatense, cercano (pero profesional), cero acartonado. Usás modismos, pero sin caer en la exageración ni la chabacanería.
Tu objetivo es explicarle a ESTA persona por qué esta propiedad le puede cerrar (o no). 

Reglas:
- Hablarle de "vos", no en genérico.
- Máximo 280 caracteres.
- Mencionar 2-3 cosas que le importan al usuario y 1 posible trade-off.
- Enfocate en como afecta su estilo de vida, no solo en datos técnicos como los m2.
- No inventar datos.
- Conexión semántica: Si el usuario pidió "silencio para programar" y la propiedad es un "contrafrente en calle cortada", resaltá esa conexión explícitamente.
- Evitar frases marketineras.
- Evitar modismos excesivos.
- Si falta un must-have, decirlo con tacto.
- No usar listas, solo 2-3 frases cortas.
- No ignores "red flags" aunque el match sea alto.
- Responder SOLO en JSON válido con esta estructura exacta:
{{
  "why_match": "2-3 frases cortas sobre por qué matchea con este usuario",
  "warnings": "1 frase corta con trade-off o red flag (opcional, string vacío si no hay)",
  "conclusion": "1 frase final con el veredicto final"
}}

[USER]
- Hogar ideal: {ideal_description}
- Must-haves: {must_haves}
- Presupuesto: {budget}
- Ambientes: {rooms}
- Barrios: {neighborhoods}

[PROPIEDAD]
- Título: {title}
- Barrio: {listing_neighborhood}
- Precio: {price}
- Ambientes: {listing_rooms}
- Features: {features}
- Descripción: {description}
- Similitud vectorial: {similarity}

Escribí un mensaje personalizado para esta persona."""


@dataclass
class PersonalizedAnalysis:
    """Resultado estructurado de análisis personalizado."""

    why_match: str
    warnings: str
    conclusion: str


class PersonalizedMatchAnalyzer:
    """Analiza un listing en contexto de preferencias de un usuario."""

    def __init__(self):
        self._provider: BaseLLMProvider = get_llm_provider()

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

        budget = (
            f"hasta USD {hard.max_price_usd}"
            if hard.max_price_usd is not None
            else "sin limite"
        )

        neighborhoods = ", ".join(hard.neighborhoods) if hard.neighborhoods else "todos CABA"

        return {
            "ideal_description": soft.ideal_description or "sin descripcion",
            "must_haves": ", ".join(must_haves) if must_haves else "ninguno",
            "budget": budget,
            "rooms": rooms,
            "neighborhoods": neighborhoods,
        }

    def _build_listing_context(self, listing_data: dict) -> dict:
        features = listing_data.get("features", {}) or {}

        feature_items = []
        for key, value in features.items():
            if value:
                feature_items.append(key)

        currency = listing_data.get("currency", "USD")
        price_raw = listing_data.get("price")
        if currency == "ARS" and price_raw:
            price = f"ARS {price_raw}"
        else:
            price = f"USD {price_raw}"

        return {
            "title": listing_data.get("title", ""),
            "listing_neighborhood": listing_data.get("neighborhood", ""),
            "price": price,
            "listing_rooms": listing_data.get("rooms", ""),
            "features": ", ".join(feature_items) if feature_items else "ninguna",
            "description": (listing_data.get("description", "") or "")[:1400],
        }

    async def generate(
        self,
        preferences: UserPreferences,
        listing_data: dict,
        similarity_score: float,
    ) -> PersonalizedAnalysis:
        """Genera un analisis estructurado para notificación."""
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
                similarity=f"{similarity_score:.3f}",
            )

            response = await self._provider.generate(
                system_prompt=PERSONALIZED_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.4,
                max_tokens=220,
            )

            text = (response.text or "").strip()
            if text.startswith("```"):
                parts = text.split("```")
                if len(parts) >= 2:
                    text = parts[1].strip()
                    if text.startswith("json"):
                        text = text[4:].strip()

            if not text:
                return PersonalizedAnalysis(
                    why_match="Está alineada con varias de tus prioridades principales.",
                    warnings="",
                    conclusion="Vale revisarla en detalle para validar encaje final.",
                )

            data = json.loads(text)
            why_match = str(data.get("why_match", "")).strip()
            warnings = str(data.get("warnings", "")).strip()
            conclusion = str(data.get("conclusion", "")).strip()

            if not why_match:
                why_match = "Está alineada con varias de tus prioridades principales."
            if not conclusion:
                conclusion = "Vale revisarla en detalle para validar encaje final."

            return PersonalizedAnalysis(
                why_match=why_match[:420],
                warnings=warnings[:220],
                conclusion=conclusion[:200],
            )

        except Exception as e:
            logger.warning("Error generando analisis personalizado", error=str(e))
            return PersonalizedAnalysis(
                why_match="Tiene buena afinidad con lo que buscas.",
                warnings="",
                conclusion="Vale la pena abrir la publicación y validar los detalles clave.",
            )
