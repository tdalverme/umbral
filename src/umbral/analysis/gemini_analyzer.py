"""
Analizador de listings con Gemini.

Extrae el "valor invisible" de los anuncios inmobiliarios:
- Scores cualitativos (silencio, luz, conectividad)
- Características inferidas
- Resumen ejecutivo honesto
"""

import json
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from umbral.config import get_settings
from umbral.models import (
    RawListing,
    AnalyzedListing,
    PropertyScores,
    InferredFeatures,
)

logger = structlog.get_logger()

# System prompt para Gemini
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


@dataclass
class AnalysisResult:
    """Resultado del análisis de Gemini."""

    scores: PropertyScores
    features: InferredFeatures
    style_tags: list[str]
    executive_summary: str
    raw_response: str


class GeminiAnalyzer:
    """
    Analizador de propiedades usando Google Gemini.

    Extrae información cualitativa de los anuncios que no está
    explícita en los datos estructurados.
    """

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        api_key = api_key or settings.gemini_api_key

        self.client = genai.Client(api_key=api_key)
        # Usar modelo estable - gemini-2.0-flash-exp o gemini-1.5-flash
        self.model_name = "gemini-2.5-flash-lite"
        self._settings = settings
        logger.info("Gemini analyzer inicializado", model=self.model_name)

    def _fix_truncated_json(self, text: str) -> str:
        """Intenta arreglar JSON truncado agregando cierres faltantes."""
        # Contar llaves y corchetes abiertos
        open_braces = text.count('{') - text.count('}')
        open_brackets = text.count('[') - text.count(']')
        
        # Agregar cierres faltantes
        fixed = text
        
        # Si estamos en medio de un string, cerrarlo
        if fixed.count('"') % 2 == 1:
            fixed += '"'
        
        # Si estamos en medio de un número, no agregar nada
        if fixed and fixed[-1].isdigit():
            pass
        elif fixed and fixed[-1] == '.':
            fixed += "5"  # Completar número truncado
        
        # Cerrar arrays y objetos
        fixed += ']' * open_brackets
        fixed += '}' * open_braces
        
        return fixed

    def _build_prompt(self, listing: RawListing) -> str:
        """Construye el prompt para analizar un listing."""
        # Formatear features como texto
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

        Raises:
            ValueError: Si la respuesta de Gemini no es válida
        """
        prompt = self._build_prompt(listing)

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=[ANALYSIS_SYSTEM_PROMPT, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.2,  # Más bajo para respuestas más consistentes
                    top_p=0.8,
                    max_output_tokens=4096,  # Aumentado para evitar truncamiento
                ),
            )

            raw_text = response.text.strip()
            
            logger.debug(f"Respuesta de Gemini: {raw_text[:500]}...")

            # Limpiar respuesta (a veces viene con markdown)
            if raw_text.startswith("```"):
                parts = raw_text.split("```")
                if len(parts) >= 2:
                    raw_text = parts[1]
                    if raw_text.startswith("json"):
                        raw_text = raw_text[4:]
            raw_text = raw_text.strip()
            
            # Verificar si la respuesta parece truncada
            if not raw_text.endswith("}"):
                logger.warning(
                    "Respuesta de Gemini parece truncada",
                    external_id=listing.external_id,
                    response_end=raw_text[-100:] if len(raw_text) > 100 else raw_text,
                )
                # Intentar arreglar JSON truncado
                raw_text = self._fix_truncated_json(raw_text)

            # Parsear JSON
            data = json.loads(raw_text)

            # Validar y construir objetos
            scores = PropertyScores(**data["scores"])
            features = InferredFeatures(**data["features"])
            style_tags = data.get("style_tags", [])[:5]
            summary = data.get("executive_summary", "")[:280]

            logger.info(
                "Listing analizado",
                external_id=listing.external_id,
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
                "Error parseando respuesta de Gemini",
                external_id=listing.external_id,
                error=str(e),
                response=raw_text if 'raw_text' in locals() else "N/A",
            )
            # Devolver valores por defecto en caso de error
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
            logger.error(
                "Error en análisis de Gemini",
                external_id=listing.external_id,
                error=str(e),
            )
            raise

    def create_analyzed_listing(
        self,
        raw_listing: RawListing,
        raw_listing_id: str,
        analysis: AnalysisResult,
    ) -> AnalyzedListing:
        """
        Crea un AnalyzedListing combinando raw data y análisis.

        Args:
            raw_listing: Listing crudo original
            raw_listing_id: UUID del raw_listing en Supabase
            analysis: Resultado del análisis de Gemini

        Returns:
            AnalyzedListing listo para insertar en Supabase
        """
        # Parsear precio
        try:
            price_original = float(raw_listing.price.replace(".", "").replace(",", "."))
        except ValueError:
            price_original = 0.0

        # Calcular precio en USD
        price_usd = AnalyzedListing.calculate_price_usd(
            price_original,
            raw_listing.currency,
            self._settings.ars_to_usd_rate,
        )

        # Calcular precio por m2
        try:
            size = float(raw_listing.size_covered or raw_listing.size_total or "0")
        except ValueError:
            size = 0.0

        price_per_m2 = AnalyzedListing.calculate_price_per_m2(price_usd, size)

        # Parsear ambientes
        try:
            rooms = int(raw_listing.rooms)
        except ValueError:
            rooms = 1

        return AnalyzedListing(
            raw_listing_id=raw_listing_id,
            external_id=raw_listing.external_id,
            currency_original=raw_listing.currency,
            price_original=price_original,
            price_usd=price_usd,
            price_per_m2_usd=price_per_m2,
            neighborhood=raw_listing.neighborhood,
            rooms=rooms,
            scores=analysis.scores,
            features=analysis.features,
            style_tags=analysis.style_tags,
            executive_summary=analysis.executive_summary,
            analysis_version=self._settings.analysis_version,
        )
