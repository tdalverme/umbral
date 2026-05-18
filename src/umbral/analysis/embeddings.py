"""
Generador de embeddings semánticos y multimodales.

Usa Gemini embeddings para representar:
- Listings (texto + imágenes principales)
- Preferencias de usuario (texto)
- Queries libres
"""

import mimetypes
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types
import structlog
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from umbral.config import get_settings
from umbral.models import RawListing, AnalyzedListing, UserPreferences

logger = structlog.get_logger()


class EmbeddingGenerator:
    """
    Genera embeddings usando Gemini Embeddings (matryoshka ready).

    Los embeddings se usan para:
    - Búsqueda semántica de propiedades ("busco algo luminoso y tranquilo")
    - Matching entre preferencias del usuario y propiedades
    - Detección de propiedades similares
    """

    # Dimensión nativa máxima del modelo Gemini embedding
    NATIVE_MAX_DIM = 3072
    DEFAULT_OUTPUT_DIM = 768
    ALLOWED_MATRYOSHKA_DIMS = {512, 768, 1536, 3072}
    SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}
    SUPPORTED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
    IMAGE_NOISE_KEYWORDS = (
        "logo",
        "watermark",
        "plan",
        "plano",
        "floorplan",
        "mapa",
        "streetview",
        "sin-foto",
        "placeholder",
        "vectorial",
        ".svg",
        "technical-specs",
    )
    IMAGE_PRIORITY_KEYWORDS = (
        "living",
        "frente",
        "fachada",
        "cocina",
        "comedor",
        "balcon",
        "terraza",
    )

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        api_key = api_key or settings.gemini_api_key
        
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY es requerida para embeddings. "
                "Groq no tiene modelos de embedding, usamos Gemini para esto."
            )

        self.client = genai.Client(api_key=api_key)
        self.model_name = settings.embedding_model
        self.output_dim = int(settings.embedding_output_dim or self.DEFAULT_OUTPUT_DIM)
        self.storage_dim = int(settings.embedding_storage_dim or self.output_dim)
        self.max_images = int(settings.embedding_max_images)
        self.image_timeout_seconds = float(settings.embedding_image_timeout_seconds)

        if self.output_dim > self.NATIVE_MAX_DIM:
            raise ValueError(
                f"embedding_output_dim={self.output_dim} excede el máximo {self.NATIVE_MAX_DIM}"
            )
        if self.storage_dim > self.NATIVE_MAX_DIM:
            raise ValueError(
                f"embedding_storage_dim={self.storage_dim} excede el máximo {self.NATIVE_MAX_DIM}"
            )
        if self.output_dim not in self.ALLOWED_MATRYOSHKA_DIMS:
            logger.warning(
                "Dimensión no estándar para Matryoshka; verificar soporte del modelo",
                output_dim=self.output_dim,
                allowed=sorted(self.ALLOWED_MATRYOSHKA_DIMS),
            )

        logger.info(
            "Embedding generator inicializado",
            model=self.model_name,
            output_dim=self.output_dim,
            storage_dim=self.storage_dim,
            max_images=self.max_images,
        )

    def _normalize_embedding_for_storage(self, embedding: list[float]) -> list[float]:
        """
        Ajusta dimensión final para persistencia en DB.

        - Si output_dim > storage_dim: truncamos (Matryoshka)
        - Si output_dim < storage_dim: hacemos zero-padding
        """
        if len(embedding) == self.storage_dim:
            return embedding
        if len(embedding) > self.storage_dim:
            return embedding[: self.storage_dim]
        return embedding + [0.0] * (self.storage_dim - len(embedding))

    def _score_image_url(self, image_url: str) -> int:
        lowered = image_url.lower()
        if any(keyword in lowered for keyword in self.IMAGE_NOISE_KEYWORDS):
            return -100
        score = 0
        if lowered.endswith(self.SUPPORTED_IMAGE_EXTENSIONS):
            score += 2
        if any(keyword in lowered for keyword in self.IMAGE_PRIORITY_KEYWORDS):
            score += 10
        if "front" in lowered or "cover" in lowered or "principal" in lowered:
            score += 5
        return score

    def _select_main_images(self, image_urls: list[str]) -> list[str]:
        if not image_urls:
            return []
        deduped: list[str] = []
        for image_url in image_urls:
            if image_url and image_url not in deduped:
                deduped.append(image_url)

        ranked = sorted(
            deduped,
            key=lambda url: self._score_image_url(url),
            reverse=True,
        )
        filtered = [url for url in ranked if self._score_image_url(url) >= 0]
        selected = filtered if filtered else deduped
        return selected[: self.max_images]

    async def _download_image_part(self, image_url: str) -> Optional[types.Part]:
        """
        Descarga una imagen y la convierte a Part para embedding multimodal.
        """
        try:
            async with httpx.AsyncClient(timeout=self.image_timeout_seconds) as client:
                response = await client.get(image_url, follow_redirects=True)
            response.raise_for_status()

            mime_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if not mime_type or not mime_type.startswith("image/"):
                guessed, _ = mimetypes.guess_type(image_url)
                mime_type = guessed or ""

            if mime_type not in self.SUPPORTED_IMAGE_MIME_TYPES:
                logger.debug(
                    "Imagen descartada por MIME no soportado por Gemini embeddings",
                    url=image_url,
                    mime_type=mime_type,
                    supported=sorted(self.SUPPORTED_IMAGE_MIME_TYPES),
                )
                return None

            image_bytes = response.content
            if not image_bytes:
                return None

            return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        except Exception as e:
            logger.debug("No se pudo descargar imagen para embedding", url=image_url, error=str(e))
            return None

    def _guess_mime_type_from_url(self, image_url: str) -> str:
        guessed, _ = mimetypes.guess_type(image_url)
        if guessed:
            return guessed.lower()
        suffix = Path(image_url.split("?")[0]).suffix.lower()
        if suffix in (".jpg", ".jpeg"):
            return "image/jpeg"
        if suffix == ".png":
            return "image/png"
        return ""

    async def debug_image_candidates(self, image_urls: list[str]) -> dict:
        """
        Inspecciona candidatas para embedding multimodal y explica decisiones.
        """
        urls = image_urls or []
        scored = [
            {"url": url, "score": self._score_image_url(url)}
            for url in urls
        ]
        selected = self._select_main_images(urls)

        accepted: list[dict] = []
        rejected: list[dict] = []
        for item in scored:
            url = item["url"]
            if item["score"] < 0:
                rejected.append({
                    "url": url,
                    "stage": "selection",
                    "reason": "noise_keyword",
                    "score": item["score"],
                })
                continue

            guessed_mime = self._guess_mime_type_from_url(url)
            if guessed_mime and guessed_mime not in self.SUPPORTED_IMAGE_MIME_TYPES:
                rejected.append({
                    "url": url,
                    "stage": "mime_guess",
                    "reason": "unsupported_mime",
                    "mime": guessed_mime,
                })
                continue

            part = await self._download_image_part(url)
            if part is None:
                rejected.append({
                    "url": url,
                    "stage": "download_or_mime_validation",
                    "reason": "download_failed_or_invalid_mime",
                })
            else:
                accepted.append({
                    "url": url,
                    "mime": part.inline_data.mime_type if part.inline_data else None,
                })

        return {
            "supported_mime_types": sorted(self.SUPPORTED_IMAGE_MIME_TYPES),
            "input_count": len(urls),
            "scored": scored,
            "selected_count": len(selected),
            "selected_urls": selected,
            "accepted_count": len(accepted),
            "accepted": accepted,
            "rejected_count": len(rejected),
            "rejected": rejected,
        }

    async def _build_multimodal_contents(self, text: str, image_urls: list[str]):
        """
        Construye payload multimodal para embed_content.
        """
        if not image_urls or self.max_images <= 0:
            return text

        selected_images = self._select_main_images(image_urls)
        if not selected_images:
            return text

        parts: list[types.Part] = [types.Part.from_text(text=text)]
        images_added = 0
        for image_url in selected_images:
            image_part = await self._download_image_part(image_url)
            if image_part is not None:
                parts.append(image_part)
                images_added += 1

        if images_added == 0:
            return text

        logger.debug(
            "Contenido multimodal construido",
            requested_images=len(image_urls),
            selected_images=len(selected_images),
            embedded_images=images_added,
        )
        return [types.Content(role="user", parts=parts)]

    async def _build_image_only_contents(self, image_urls: list[str]):
        """
        Construye payload solo con imagenes para embed_content.
        """
        if not image_urls or self.max_images <= 0:
            return None

        selected_images = self._select_main_images(image_urls)
        if not selected_images:
            return None

        parts: list[types.Part] = []
        images_added = 0
        for image_url in selected_images:
            image_part = await self._download_image_part(image_url)
            if image_part is not None:
                parts.append(image_part)
                images_added += 1

        if images_added == 0:
            return None

        logger.debug(
            "Contenido de imagen-only construido",
            requested_images=len(image_urls),
            selected_images=len(selected_images),
            embedded_images=images_added,
        )
        return [types.Content(role="user", parts=parts)]

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
        if soft.weight_walkability >= 0.7:
            preferences_text.append("muy caminable para compras cotidianas")
        if soft.weight_urban_activity >= 0.7:
            preferences_text.append("con vida urbana, cafes y comercios cerca")
        if soft.noise_tolerance <= 0.3:
            preferences_text.append("evitar ruido urbano intenso")

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
        image_urls: Optional[list[str]] = None,
    ) -> list[float]:
        """
        Genera embedding para un listing.

        Args:
            raw_listing: Listing crudo
            analyzed_listing: Listing analizado (opcional, mejora la calidad)

        Returns:
            Vector con dimensión storage_dim
        """
        text = self._build_listing_text(raw_listing, analyzed_listing)
        effective_images = image_urls if image_urls is not None else (raw_listing.images or [])

        try:
            contents = await self._build_multimodal_contents(text=text, image_urls=effective_images)
            try:
                response = await self.client.aio.models.embed_content(
                    model=self.model_name,
                    contents=contents,
                    config=types.EmbedContentConfig(output_dimensionality=self.output_dim),
                )
            except Exception as multimodal_error:
                logger.warning(
                    "Fallo embedding multimodal; fallback a texto",
                    external_id=raw_listing.external_id,
                    error=str(multimodal_error),
                )
                response = await self.client.aio.models.embed_content(
                    model=self.model_name,
                    contents=text,
                    config=types.EmbedContentConfig(output_dimensionality=self.output_dim),
                )

            embedding = self._normalize_embedding_for_storage(list(response.embeddings[0].values))

            logger.debug(
                "Embedding generado para listing",
                external_id=raw_listing.external_id,
                text_length=len(text),
                image_count=len(effective_images),
                embedding_dim=len(embedding),
            )

            return embedding

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
            Vector con dimensión storage_dim
        """
        text = self._build_preference_text(preferences)

        try:
            response = await self.client.aio.models.embed_content(
                model=self.model_name,
                contents=text,
                config=types.EmbedContentConfig(output_dimensionality=self.output_dim),
            )

            embedding = self._normalize_embedding_for_storage(list(response.embeddings[0].values))

            logger.debug(
                "Embedding generado para preferencias",
                text_length=len(text),
                embedding_dim=len(embedding),
            )

            return embedding

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
            Vector con dimensión storage_dim
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

            embedding = self._normalize_embedding_for_storage(list(response.embeddings[0].values))

            logger.debug(
                "Vibe embedding generado",
                text_length=len(text),
                tags_count=len(style_tags),
                embedding_dim=len(embedding),
            )

            return embedding

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
            Vector con dimensión storage_dim
        """
        try:
            response = await self.client.aio.models.embed_content(
                model=self.model_name,
                contents=query,
                config=types.EmbedContentConfig(output_dimensionality=self.output_dim),
            )

            return self._normalize_embedding_for_storage(list(response.embeddings[0].values))

        except Exception as e:
            logger.error(
                "Error generando embedding de query",
                query=query[:50],
                error=str(e),
            )
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_images_only_embedding(self, image_urls: list[str]) -> list[float]:
        """
        Genera embedding usando solo imagenes (sin texto del listing).

        Se usa para debugging de señal visual pura.
        """
        contents = await self._build_image_only_contents(image_urls=image_urls or [])
        if not contents:
            raise ValueError("No hay imagenes validas para generar embedding image-only")

        try:
            response = await self.client.aio.models.embed_content(
                model=self.model_name,
                contents=contents,
                config=types.EmbedContentConfig(output_dimensionality=self.output_dim),
            )
            return self._normalize_embedding_for_storage(list(response.embeddings[0].values))
        except Exception as e:
            logger.error("Error generando embedding image-only", error=str(e))
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

        if not vec1 or not vec2:
            return 0.0

        common_dim = min(len(vec1), len(vec2))
        v1 = vec1[:common_dim]
        v2 = vec2[:common_dim]

        dot_product = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)
