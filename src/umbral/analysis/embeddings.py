"""
Generador de embeddings para búsqueda semántica.

Usa el modelo text-embedding-004 de Google para generar
vectores de 768 dimensiones.
"""

from typing import Optional

from google import genai
from google.genai import types
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from umbral.config import get_settings
from umbral.models import RawListing, AnalyzedListing, UserPreferences

logger = structlog.get_logger()


class EmbeddingGenerator:
    """
    Genera embeddings usando Google's text-embedding-004.

    Los embeddings se usan para:
    - Búsqueda semántica de propiedades ("busco algo luminoso y tranquilo")
    - Matching entre preferencias del usuario y propiedades
    - Detección de propiedades similares
    """

    # Dimensión del vector (gemini-embedding-001 soporta 768, 1536, 3072)
    EMBEDDING_DIM = 768

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        api_key = api_key or settings.gemini_api_key
        
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY es requerida para embeddings. "
                "Groq no tiene modelos de embedding, usamos Gemini para esto."
            )

        self.client = genai.Client(api_key=api_key)
        # Modelo de embedding según docs oficiales: gemini-embedding-001
        # https://ai.google.dev/gemini-api/docs/embeddings
        self.model_name = "gemini-embedding-001"
        self.output_dim = self.EMBEDDING_DIM
        logger.info("Embedding generator inicializado", model=self.model_name, dim=self.output_dim)

    def _build_listing_text(
        self,
        raw_listing: RawListing,
        analyzed_listing: Optional[AnalyzedListing] = None,
    ) -> str:
        """
        Construye el texto para embedding de un listing.

        Combina información estructurada y análisis cualitativo
        para crear una representación semántica rica.
        """
        parts = []

        # Ubicación
        parts.append(f"Ubicación: {raw_listing.neighborhood}, CABA")

        # Características físicas
        parts.append(f"Departamento de {raw_listing.rooms} ambientes")

        if raw_listing.size_covered or raw_listing.size_total:
            size = raw_listing.size_covered or raw_listing.size_total
            parts.append(f"Superficie: {size} metros cuadrados")

        if raw_listing.disposition:
            parts.append(f"Disposición: {raw_listing.disposition}")

        if raw_listing.orientation:
            parts.append(f"Orientación: {raw_listing.orientation}")

        # Features del listing
        features = raw_listing.features.model_dump()
        feature_texts = []
        if features.get("has_balcony"):
            feature_texts.append("con balcón")
        if features.get("has_terrace"):
            feature_texts.append("con terraza")
        if features.get("is_pet_friendly"):
            feature_texts.append("acepta mascotas")
        if features.get("has_elevator"):
            feature_texts.append("con ascensor")
        if features.get("has_pool"):
            feature_texts.append("con pileta")
        if features.get("has_gym"):
            feature_texts.append("con gimnasio")
        if features.get("is_furnished"):
            feature_texts.append("amoblado")

        if feature_texts:
            parts.append(", ".join(feature_texts))

        # Si tenemos análisis, agregar información cualitativa
        if analyzed_listing:
            # Style tags
            if analyzed_listing.style_tags:
                parts.append(f"Estilo: {', '.join(analyzed_listing.style_tags)}")

            # Scores como texto
            scores = analyzed_listing.scores
            if scores.quietness >= 0.7:
                parts.append("muy tranquilo y silencioso")
            elif scores.quietness <= 0.3:
                parts.append("zona con ruido")

            if scores.luminosity >= 0.7:
                parts.append("muy luminoso")
            elif scores.luminosity <= 0.3:
                parts.append("poca luz natural")

            if scores.wfh_suitability >= 0.7:
                parts.append("ideal para trabajar desde casa")

            if scores.green_spaces >= 0.7:
                parts.append("cerca de espacios verdes")

            # Features inferidas
            inferred = analyzed_listing.features
            parts.append(f"Ambiente {inferred.neighborhood_vibe}")
            parts.append(f"Vista {inferred.view_type}")

            if inferred.is_family_friendly:
                parts.append("apto para familias")

            # Resumen
            parts.append(analyzed_listing.executive_summary)

        # Descripción original (truncada)
        desc_truncated = raw_listing.description[:500]
        parts.append(desc_truncated)

        return ". ".join(parts)

    def _build_preference_text(self, preferences: UserPreferences) -> str:
        """
        Construye el texto para embedding de preferencias de usuario.
        """
        parts = []

        hard = preferences.hard_filters
        soft = preferences.soft_preferences

        # Ubicación
        if hard.neighborhoods:
            parts.append(f"Busco en: {', '.join(hard.neighborhoods)}")

        # Precio
        if hard.max_price_usd:
            parts.append(f"Presupuesto máximo: {hard.max_price_usd} USD")

        # Ambientes
        if hard.min_rooms:
            parts.append(f"Mínimo {hard.min_rooms} ambientes")

        # Tipo de operación
        parts.append(f"Para {hard.operation_type}")

        # Requisitos
        requirements = []
        if hard.requires_balcony:
            requirements.append("balcón")
        if hard.requires_parking:
            requirements.append("cochera")
        if hard.requires_pets_allowed:
            requirements.append("que acepte mascotas")
        if hard.requires_furnished:
            requirements.append("amoblado")

        if requirements:
            parts.append(f"Necesito: {', '.join(requirements)}")

        # Preferencias soft como texto descriptivo
        preferences_text = []

        if soft.weight_quietness >= 0.7:
            preferences_text.append("muy tranquilo y silencioso")
        if soft.weight_luminosity >= 0.7:
            preferences_text.append("muy luminoso")
        if soft.weight_connectivity >= 0.7:
            preferences_text.append("bien conectado con transporte")
        if soft.weight_wfh_suitability >= 0.7:
            preferences_text.append("ideal para trabajar desde casa")
        if soft.weight_modernity >= 0.7:
            preferences_text.append("moderno o reciclado")
        if soft.weight_green_spaces >= 0.7:
            preferences_text.append("cerca de espacios verdes")

        if preferences_text:
            parts.append(f"Prefiero: {', '.join(preferences_text)}")

        # Descripción libre del usuario
        if soft.ideal_description:
            parts.append(soft.ideal_description)

        return ". ".join(parts)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_listing_embedding(
        self,
        raw_listing: RawListing,
        analyzed_listing: Optional[AnalyzedListing] = None,
    ) -> list[float]:
        """
        Genera embedding para un listing.

        Args:
            raw_listing: Listing crudo
            analyzed_listing: Listing analizado (opcional, mejora la calidad)

        Returns:
            Vector de 768 dimensiones
        """
        text = self._build_listing_text(raw_listing, analyzed_listing)

        try:
            response = await self.client.aio.models.embed_content(
                model=self.model_name,
                contents=text,
                config=types.EmbedContentConfig(output_dimensionality=self.output_dim),
            )

            embedding = response.embeddings[0].values

            logger.debug(
                "Embedding generado para listing",
                external_id=raw_listing.external_id,
                text_length=len(text),
                embedding_dim=len(embedding),
            )

            return list(embedding)

        except Exception as e:
            logger.error(
                "Error generando embedding de listing",
                external_id=raw_listing.external_id,
                error=str(e),
            )
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_preference_embedding(
        self, preferences: UserPreferences
    ) -> list[float]:
        """
        Genera embedding para las preferencias de un usuario.

        Args:
            preferences: Preferencias del usuario

        Returns:
            Vector de 768 dimensiones
        """
        text = self._build_preference_text(preferences)

        try:
            response = await self.client.aio.models.embed_content(
                model=self.model_name,
                contents=text,
                config=types.EmbedContentConfig(output_dimensionality=self.output_dim),
            )

            embedding = response.embeddings[0].values

            logger.debug(
                "Embedding generado para preferencias",
                text_length=len(text),
                embedding_dim=len(embedding),
            )

            return list(embedding)

        except Exception as e:
            logger.error(
                "Error generando embedding de preferencias",
                error=str(e),
            )
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_vibe_embedding(
        self,
        executive_summary: str,
        style_tags: list[str],
    ) -> list[float]:
        """
        Genera embedding solo del "vibe" de una propiedad.
        
        Este embedding captura la esencia cualitativa del listing
        sin incluir datos estructurales (m², ambientes, ubicación).
        
        Se usa para matching semántico contra la descripción del
        hogar ideal del usuario.

        Args:
            executive_summary: Resumen generado por IA
            style_tags: Tags de estilo (luminoso, moderno, etc.)

        Returns:
            Vector de 768 dimensiones
        """
        # Construir texto enfocado en el vibe
        parts = []
        
        if style_tags:
            parts.append(f"Estilo: {', '.join(style_tags)}")
        
        if executive_summary:
            parts.append(executive_summary)
        
        text = ". ".join(parts)
        
        if not text:
            # Fallback si no hay contenido
            text = "Propiedad estándar sin características distintivas"

        try:
            response = await self.client.aio.models.embed_content(
                model=self.model_name,
                contents=text,
                config=types.EmbedContentConfig(output_dimensionality=self.output_dim),
            )

            embedding = response.embeddings[0].values

            logger.debug(
                "Vibe embedding generado",
                text_length=len(text),
                tags_count=len(style_tags),
                embedding_dim=len(embedding),
            )

            return list(embedding)

        except Exception as e:
            logger.error(
                "Error generando vibe embedding",
                error=str(e),
            )
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_query_embedding(self, query: str) -> list[float]:
        """
        Genera embedding para una query de búsqueda libre.

        Args:
            query: Texto de búsqueda (ej: "departamento luminoso en Palermo")

        Returns:
            Vector de 768 dimensiones
        """
        try:
            response = await self.client.aio.models.embed_content(
                model=self.model_name,
                contents=query,
                config=types.EmbedContentConfig(output_dimensionality=self.output_dim),
            )

            return list(response.embeddings[0].values)

        except Exception as e:
            logger.error(
                "Error generando embedding de query",
                query=query[:50],
                error=str(e),
            )
            raise

    @staticmethod
    def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """
        Calcula la similitud de coseno entre dos vectores.

        Args:
            vec1: Primer vector
            vec2: Segundo vector

        Returns:
            Similitud de coseno (0.0 a 1.0)
        """
        import math

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)
