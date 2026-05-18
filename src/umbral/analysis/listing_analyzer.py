"""
Analizador de listings con LLM.

Extrae el "valor invisible" de los anuncios inmobiliarios:
- Scores cualitativos (silencio, luz, conectividad)
- Características inferidas
- Resumen ejecutivo honesto

Soporta múltiples proveedores: Gemini, Groq (Llama)
"""

import json
import re
from dataclasses import dataclass
from typing import Optional

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from umbral.config import get_settings
from umbral.models import (
    RawListing,
    AnalyzedListing,
    PropertyScores,
    InferredFeatures,
)
from umbral.analysis.llm_providers import get_llm_provider, BaseLLMProvider

logger = structlog.get_logger()

MAX_DESCRIPTION_CHARS_FOR_ANALYSIS = 3500
MAX_PROMPT_CHARS_FOR_ANALYSIS = 6500
MAX_ULTRA_COMPACT_DESCRIPTION_CHARS = 450

# System prompt para análisis de propiedades
ANALYSIS_SYSTEM_PROMPT = """Eres un experto analista inmobiliario argentino con años de experiencia en el mercado de CABA.
Tu trabajo es analizar anuncios de propiedades y extraer información valiosa que NO está explícita en el anuncio.

CONTEXTO DE BUENOS AIRES:
- Las avenidas son ruidosas, las calles internas son más tranquilas
- "Frente" generalmente significa más luz pero más ruido
- "Contrafrente" o "interno" significa menos ruido pero potencialmente menos luz
- Los pisos altos (8+) suelen ser más silenciosos
- Barrios como Palermo, Recoleta, Belgrano son bien conectados
- "A estrenar" o "reciclado" indica modernidad
- Edificios con amenities (pileta, gym, sum) suelen tener expensas altas
- La orientación Norte es la más buscada por la luz

INSTRUCCIONES:
Analiza el siguiente anuncio y devuelve un JSON con esta estructura exacta:

{
    "scores": {
        "quietness": 0.0-1.0,      // Nivel de silencio esperado (1.0 = muy silencioso)
        "luminosity": 0.0-1.0,     // Luz natural esperada (1.0 = muy luminoso)
        "connectivity": 0.0-1.0,   // Acceso a transporte (1.0 = excelente)
        "wfh_suitability": 0.0-1.0,// Aptitud para home office (1.0 = ideal)
        "modernity": 0.0-1.0,      // Nivel de modernidad (1.0 = a estrenar)
        "green_spaces": 0.0-1.0    // Cercanía a espacios verdes (1.0 = excelente)
    },
    "features": {
        "is_investment_opportunity": true/false,
        "is_family_friendly": true/false,
        "has_high_storage_capacity": true/false,
        "neighborhood_vibe": "residencial|comercial|joven|trendy|lujo|familiar",
        "view_type": "abierta|pulmón|frente|interna|contrafrente"
    },
    "style_tags": ["luminoso", "minimalista", "acogedor", "moderno", "clásico", "reciclado", "amplio", "compacto"],
    "executive_summary": "Resumen honesto de máximo 280 caracteres. Destaca lo bueno Y lo malo."
}

REGLAS IMPORTANTES:
1. Sé HONESTO. Si no hay suficiente información, usa valores medios (0.5).
2. Infiere el ruido basándote en: piso, frente/contrafrente, tipo de calle (si se menciona avenida).
3. El resumen debe ser útil para alguien que busca, no un texto de marketing.
4. Los style_tags deben ser 3-5 palabras que describan la "vibra" del lugar.
5. Responde SOLO con el JSON, sin texto adicional."""

ANALYSIS_SYSTEM_PROMPT_COMPACT = """Analiza un anuncio inmobiliario de CABA.
Responde SOLO JSON valido con scores, features, style_tags y executive_summary.
Scores requeridos: quietness, luminosity, connectivity, wfh_suitability, modernity, green_spaces.
Features requeridas: is_investment_opportunity, is_family_friendly, has_high_storage_capacity, neighborhood_vibe, view_type.
Si falta informacion usa valores medios y no inventes."""


@dataclass
class AnalysisResult:
    """Resultado del análisis de LLM."""

    scores: PropertyScores
    features: InferredFeatures
    style_tags: list[str]
    executive_summary: str
    raw_response: str


class ListingAnalyzer:
    """
    Analizador de propiedades usando LLM (Gemini o Groq).

    Extrae información cualitativa de los anuncios que no está
    explícita en los datos estructurados.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        Inicializa el analizador.
        
        Args:
            provider: 'gemini' o 'groq' (default: settings.llm_provider)
            api_key: API key del proveedor
            model: Modelo a usar
        """
        self._settings = get_settings()
        self._provider: BaseLLMProvider = get_llm_provider(
            provider=provider,
            api_key=api_key,
            model=model,
        )
        logger.info(
            "ListingAnalyzer inicializado",
            provider=self._provider.provider_name,
            model=getattr(self._provider, 'model', 'unknown'),
        )

    def _fix_truncated_json(self, text: str) -> str:
        """Intenta arreglar JSON truncado agregando cierres faltantes."""
        open_braces = text.count('{') - text.count('}')
        open_brackets = text.count('[') - text.count(']')
        
        fixed = text
        
        if fixed.count('"') % 2 == 1:
            fixed += '"'
        
        if fixed and fixed[-1].isdigit():
            pass
        elif fixed and fixed[-1] == '.':
            fixed += "5"
        
        fixed += ']' * open_brackets
        fixed += '}' * open_braces
        
        return fixed

    def _build_prompt(self, listing: RawListing) -> str:
        """Construye el prompt para analizar un listing."""
        features_text = []
        features_dict = listing.features.model_dump()
        for key, value in features_dict.items():
            if value:
                feature_name = key.replace("_", " ").replace("has ", "").replace("is ", "")
                features_text.append(feature_name)

        return f"""ANUNCIO A ANALIZAR:

TÍTULO: {listing.title}

UBICACIÓN: {listing.neighborhood}, {listing.location}

PRECIO: {listing.currency} {listing.price}
EXPENSAS: {listing.maintenance_fee or 'No especificadas'}

CARACTERÍSTICAS:
- Ambientes: {listing.rooms}
- Baños: {listing.bathrooms}
- Superficie total: {listing.size_total or 'No especificada'} m²
- Superficie cubierta: {listing.size_covered or 'No especificada'} m²
- Antigüedad: {listing.age or 'No especificada'}
- Disposición: {listing.disposition or 'No especificada'}
- Orientación: {listing.orientation or 'No especificada'}
- Cochera: {'Sí' if listing.parking_spaces else 'No'}

AMENITIES: {', '.join(features_text) if features_text else 'No especificados'}

DESCRIPCIÓN COMPLETA:
{listing.description}

---
Analiza este anuncio y devuelve el JSON con tu análisis."""

    def _build_ultra_compact_prompt(self, listing: RawListing) -> str:
        """Payload minimo para reintentar cuando Groq rechaza por 413."""
        features = [
            key.replace("_", " ")
            for key, value in listing.features.model_dump().items()
            if value
        ]
        description = " ".join((listing.description or "").split())
        if len(description) > MAX_ULTRA_COMPACT_DESCRIPTION_CHARS:
            description = description[:MAX_ULTRA_COMPACT_DESCRIPTION_CHARS].rsplit(" ", 1)[0]
            description += " [truncado]"

        return "\n".join(
            [
                "ANUNCIO:",
                f"Titulo: {listing.title[:120]}",
                f"Barrio/ubicacion: {listing.neighborhood}, {listing.location[:120]}",
                f"Precio: {listing.currency} {listing.price}; expensas: {listing.maintenance_fee or 'N/E'}",
                f"Ambientes/banos: {listing.rooms}/{listing.bathrooms}; m2: {listing.size_total or 'N/E'} total, {listing.size_covered or 'N/E'} cubiertos",
                f"Antiguedad/disposicion/orientacion: {listing.age or 'N/E'}; {listing.disposition or 'N/E'}; {listing.orientation or 'N/E'}",
                f"Cochera: {'Si' if listing.parking_spaces else 'No'}; features: {', '.join(features[:8]) if features else 'N/E'}",
                f"Descripcion: {description}",
                "Devolve solo el JSON de analisis.",
            ]
        )

    @staticmethod
    def _is_request_too_large(error_text: str) -> bool:
        return (
            "413" in error_text
            or "request_too_large" in error_text
            or "Request Entity Too Large" in error_text
        )

    async def _generate_analysis_response(
        self,
        *,
        listing: RawListing,
        prompt: str,
        system_prompt: str,
        max_tokens: int,
    ):
        try:
            return await self._provider.generate(
                system_prompt=system_prompt,
                user_prompt=prompt,
                temperature=0.2,
                max_tokens=max_tokens,
            )
        except Exception as e:
            error_text = str(e)
            if self._is_request_too_large(error_text):
                fallback_prompt = self._build_ultra_compact_prompt(listing)
                logger.warning(
                    "Proveedor rechazo payload; reintentando con prompt ultra compacto",
                    external_id=listing.external_id,
                    model=getattr(self._provider, "model", "unknown"),
                    prompt_chars=len(prompt),
                    compact_prompt_chars=len(fallback_prompt),
                )
                return await self._provider.generate(
                    system_prompt=ANALYSIS_SYSTEM_PROMPT_COMPACT,
                    user_prompt=fallback_prompt,
                    temperature=0.2,
                    max_tokens=512,
                )
            logger.error(
                "Error al generar respuesta de analisis",
                external_id=listing.external_id,
                model=getattr(self._provider, "model", "unknown"),
                error=error_text,
            )
            raise

    def _fallback_analysis(self, raw_response: str = "") -> AnalysisResult:
        """Resultado conservador cuando el proveedor no puede responder."""
        return AnalysisResult(
            scores=PropertyScores(
                quietness=0.5,
                luminosity=0.5,
                connectivity=0.5,
                wfh_suitability=0.5,
                modernity=0.5,
                green_spaces=0.5,
            ),
            features=InferredFeatures(),
            style_tags=["sin-analizar"],
            executive_summary="Analisis no disponible; se usan valores neutrales para scoring.",
            raw_response=raw_response,
        )

    def _fix_json(self, text: str) -> str:
        """
        Arregla JSON malformado que Llama a veces genera.
        
        Problemas comunes:
        - Comentarios // dentro del JSON
        - Comas faltantes entre propiedades
        """
        import re
        
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # 1. Eliminar comentarios //
            if '//' in line:
                pos = line.find('//')
                before = line[:pos]
                quote_count = before.count('"') - before.count('\\"')
                if quote_count % 2 == 0:
                    # No está dentro de un string
                    line = before.rstrip()
            cleaned_lines.append(line)
        
        # Reunir el texto
        text = '\n'.join(cleaned_lines)
        
        # 2. Agregar comas faltantes entre propiedades
        # Patrón: valor seguido de nueva línea y otra propiedad sin coma
        # Ejemplo: 0.5\n        "next" -> 0.5,\n        "next"
        
        # Agregar coma después de valores numéricos seguidos de propiedad
        text = re.sub(
            r'(\d+\.?\d*)\s*\n(\s*")',
            r'\1,\n\2',
            text
        )
        
        # Agregar coma después de strings seguidos de propiedad
        text = re.sub(
            r'(")\s*\n(\s*")',
            r'\1,\n\2',
            text
        )
        
        # Agregar coma después de true/false/null seguidos de propiedad
        text = re.sub(
            r'(true|false|null)\s*\n(\s*")',
            r'\1,\n\2',
            text
        )
        
        # Agregar coma después de } o ] seguidos de propiedad (pero no si es el cierre final)
        text = re.sub(
            r'(\}|\])\s*\n(\s*")',
            r'\1,\n\2',
            text
        )
        
        return text

    def _clean_response(self, raw_text: str) -> str:
        """Limpia la respuesta del LLM para extraer JSON."""
        text = raw_text.strip()
        
        # Remover markdown code blocks
        if text.startswith("```"):
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1]
                if text.startswith("json"):
                    text = text[4:]
        
        text = text.strip()
        
        # Arreglar JSON malformado (comentarios, comas faltantes)
        text = self._fix_json(text)
        
        # Verificar si parece truncado
        if not text.endswith("}"):
            logger.warning("Respuesta parece truncada, intentando arreglar")
            text = self._fix_truncated_json(text)
        
        return text

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def analyze(self, listing: RawListing) -> AnalysisResult:
        """
        Analiza un listing y extrae información cualitativa.

        Args:
            listing: RawListing a analizar

        Returns:
            AnalysisResult con scores, features y resumen
        """
        prompt = self._build_prompt(listing)
        if len(prompt) > MAX_PROMPT_CHARS_FOR_ANALYSIS:
            prompt = (
                prompt[:MAX_PROMPT_CHARS_FOR_ANALYSIS]
                + "\n\n[Prompt truncado por longitud; analizar con la informacion disponible.]"
            )

        try:
            response = await self._generate_analysis_response(
                listing=listing,
                prompt=prompt,
                system_prompt=ANALYSIS_SYSTEM_PROMPT,
                max_tokens=768,
            )

            raw_text = self._clean_response(response.text)
            
            logger.debug(
                f"Respuesta de {response.provider}: {raw_text[:300]}..."
            )

            data = json.loads(raw_text)

            scores = PropertyScores(**data["scores"])
            features = InferredFeatures(**data["features"])
            style_tags = data.get("style_tags", [])[:5]
            summary = data.get("executive_summary", "")[:280]

            logger.info(
                "Listing analizado",
                external_id=listing.external_id,
                provider=response.provider,
                model=response.model,
                quietness=scores.quietness,
                luminosity=scores.luminosity,
            )

            return AnalysisResult(
                scores=scores,
                features=features,
                style_tags=style_tags,
                executive_summary=summary,
                raw_response=raw_text,
            )

        except json.JSONDecodeError as e:
            logger.error(
                "Error parseando respuesta de LLM",
                external_id=listing.external_id,
                error=str(e),
                response=raw_text if 'raw_text' in locals() else "N/A",
            )
            logger.warning("Usando valores por defecto para análisis fallido")
            return AnalysisResult(
                scores=PropertyScores(
                    quietness=0.5,
                    luminosity=0.5,
                    connectivity=0.5,
                    wfh_suitability=0.5,
                    modernity=0.5,
                    green_spaces=0.5,
                ),
                features=InferredFeatures(),
                style_tags=["sin-analizar"],
                executive_summary="Análisis no disponible - error al procesar con IA.",
                raw_response=raw_text if 'raw_text' in locals() else "",
            )

        except Exception as e:
            error_text = str(e)
            logger.error(
                "Error en análisis de LLM",
                external_id=listing.external_id,
                error=error_text,
            )
            if self._is_request_too_large(error_text):
                logger.warning(
                    "Proveedor rechazo payload; usando analisis neutral",
                    external_id=listing.external_id,
                    prompt_chars=len(prompt),
                )
                return self._fallback_analysis(error_text)
            raise

    def create_analyzed_listing(
        self,
        raw_listing: RawListing,
        raw_listing_id: str,
        analysis: AnalysisResult,
    ) -> AnalyzedListing:
        """
        Crea un AnalyzedListing combinando raw data y análisis.
        """
        price_original = self._parse_amount(raw_listing.price) or 0.0

        price_usd = AnalyzedListing.calculate_price_usd(
            price_original,
            raw_listing.currency,
            self._settings.ars_to_usd_rate,
        )

        size_total = self._parse_amount(raw_listing.size_total) or 0.0
        size_covered = self._parse_amount(raw_listing.size_covered) or 0.0
        size = size_covered or size_total

        price_per_m2 = AnalyzedListing.calculate_price_per_m2(price_usd, size)
        maintenance_fee_usd = self._parse_maintenance_fee_usd(raw_listing.maintenance_fee)
        total_monthly_cost_usd = price_usd
        if raw_listing.operation_type == "alquiler":
            total_monthly_cost_usd = round(price_usd + maintenance_fee_usd, 2)

        try:
            rooms = int(raw_listing.rooms)
        except ValueError:
            rooms = 1

        coordinates = raw_listing.coordinates or {}
        latitude = coordinates.get("lat")
        longitude = coordinates.get("lng") or coordinates.get("lon")

        return AnalyzedListing(
            raw_listing_id=raw_listing_id,
            external_id=raw_listing.external_id,
            currency_original=raw_listing.currency,
            price_original=price_original,
            price_usd=price_usd,
            price_per_m2_usd=price_per_m2,
            maintenance_fee_usd=maintenance_fee_usd,
            total_monthly_cost_usd=total_monthly_cost_usd,
            size_total_m2=size_total,
            size_covered_m2=size_covered,
            neighborhood=raw_listing.neighborhood,
            rooms=rooms,
            latitude=latitude,
            longitude=longitude,
            scores=analysis.scores,
            features=analysis.features,
            style_tags=analysis.style_tags,
            executive_summary=analysis.executive_summary,
            analysis_version=self._settings.analysis_version,
        )

    @staticmethod
    def _parse_amount(value) -> float | None:
        text = str(value or "").strip()
        if not text:
            return None
        match = re.search(r"(\d[\d\.,]*)", text)
        if not match:
            return None
        normalized = match.group(1)
        if "," in normalized and "." in normalized:
            if normalized.rfind(",") > normalized.rfind("."):
                normalized = normalized.replace(".", "").replace(",", ".")
            else:
                normalized = normalized.replace(",", "")
        elif "," in normalized:
            normalized = normalized.replace(",", ".")
        else:
            pieces = normalized.split(".")
            if len(pieces) > 2 or (len(pieces) == 2 and len(pieces[-1]) == 3):
                normalized = normalized.replace(".", "")
        try:
            amount = float(normalized)
        except ValueError:
            return None
        return amount if amount > 0 else None

    def _parse_maintenance_fee_usd(self, value) -> float:
        amount = self._parse_amount(value) or 0.0
        if amount <= 0:
            return 0.0
        text = str(value or "").lower()
        if "usd" in text or "u$s" in text:
            return amount
        if amount > 500:
            return round(amount / self._settings.ars_to_usd_rate, 2)
        return amount


# Alias para compatibilidad con código existente
GeminiAnalyzer = ListingAnalyzer
