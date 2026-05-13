"""
Script simple para testear rapido la logica de embeddings.

Permite:
- Generar embedding de listing (texto + imagenes)
- Generar embedding de query/preferencia (texto)
- Calcular cosine similarity entre ambos
- Comparar multimodal vs texto-only (opcional)
- Comparar multimodal vs images-only (opcional)

Uso:
    python -m umbral.scripts.tests.test_embedding_logic --query "depto luminoso y tranquilo"
    python -m umbral.scripts.tests.test_embedding_logic --url "https://www.argenprop.com/..."
    python -m umbral.scripts.tests.test_embedding_logic --url "https://inmuebles.mercadolibre.com.ar/..." --source mercadolibre --compare-text-only
    python -m umbral.scripts.tests.test_embedding_logic --url "https://inmuebles.mercadolibre.com.ar/..." --source mercadolibre --compare-images-only
    python -m umbral.scripts.tests.test_embedding_logic --image-url "https://..." --image-url "https://..."
    python -m umbral.scripts.tests.test_embedding_logic --url "https://..." --debug-images-only
"""

import argparse
import asyncio
import json
import logging
import sys
import warnings
from urllib.parse import urlparse

import structlog

from umbral.analysis import EmbeddingGenerator
from umbral.config import get_settings
from umbral.models import ListingFeatures, RawListing
from umbral.scrapers import ArgenPropScraper, MercadoLibreScraper

# Suprimir warnings ruidosos en Windows/asyncio
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", message=".*unclosed.*")

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(message)s",
    force=True,
)

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def _detect_source_from_url(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if "argenprop.com" in host:
        return "argenprop"
    if "mercadolibre.com.ar" in host:
        return "mercadolibre"
    raise ValueError(
        f"No pude detectar la fuente desde el dominio '{host}'. "
        "Usa --source argenprop o --source mercadolibre."
    )


def _build_scraper(source: str):
    if source == "argenprop":
        return ArgenPropScraper()
    if source == "mercadolibre":
        return MercadoLibreScraper()
    raise ValueError(f"Fuente no soportada: {source}")


def _build_synthetic_listing(description: str, image_urls: list[str]) -> RawListing:
    return RawListing(
        external_id="test-embedding-001",
        url="https://example.com/listing/test-embedding-001",
        source="argenprop",
        title="Departamento 2 ambientes en Palermo",
        description=description,
        price="120000",
        currency="USD",
        location="Palermo, CABA",
        neighborhood="Palermo",
        rooms="2",
        features=ListingFeatures(has_balcony=True, has_elevator=True),
        images=image_urls,
    )


def _to_unit_interval(similarity: float) -> float:
    return max(0.0, min(1.0, (similarity + 1.0) / 2.0))


async def run_test(
    query: str,
    url: str | None = None,
    source: str = "auto",
    image_urls: list[str] | None = None,
    description: str = "",
    compare_text_only: bool = False,
    compare_images_only: bool = False,
    debug_images: bool = False,
    debug_images_only: bool = False,
    print_vector_head: int = 8,
) -> int:
    image_urls = image_urls or []
    logger.info("Iniciando test de embedding", has_url=bool(url), source=source)

    if url:
        selected_source = _detect_source_from_url(url) if source == "auto" else source
        scraper = _build_scraper(selected_source)
        async with scraper:
            listing = await scraper.scrape_listing(url)
        if not listing:
            logger.error("No se pudo parsear listing para test", url=url, source=selected_source)
            return 1
        # Si el usuario pasa --image-url, pisa las del scraper.
        if image_urls:
            listing.images = image_urls
    else:
        listing = _build_synthetic_listing(
            description=description
            or "Departamento luminoso, contrafrente y silencioso, ideal para home office.",
            image_urls=image_urls,
        )

    embedder = EmbeddingGenerator()

    if debug_images_only:
        images_debug = await embedder.debug_image_candidates(listing.images or [])
        payload = {
            "model": embedder.model_name,
            "output_dim": embedder.output_dim,
            "storage_dim": embedder.storage_dim,
            "listing_external_id": listing.external_id,
            "listing_title": listing.title,
            "listing_images_count": len(listing.images or []),
            "images_debug": images_debug,
            "note": "No se generaron embeddings. Modo debug-images-only.",
        }
        print("\n=== EMBEDDING TEST RESULT ===")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    listing_embedding = await embedder.generate_listing_embedding(
        raw_listing=listing,
        image_urls=listing.images or [],
    )
    query_embedding = await embedder.generate_query_embedding(query=query)

    raw_cosine = EmbeddingGenerator.cosine_similarity(query_embedding, listing_embedding)
    similarity = _to_unit_interval(raw_cosine)

    payload = {
        "model": embedder.model_name,
        "output_dim": embedder.output_dim,
        "storage_dim": embedder.storage_dim,
        "listing_external_id": listing.external_id,
        "listing_title": listing.title,
        "listing_images_count": len(listing.images or []),
        "query": query,
        "query_dim": len(query_embedding),
        "listing_dim": len(listing_embedding),
        "raw_cosine": raw_cosine,
        "similarity_0_1": similarity,
        "query_vector_head": query_embedding[:print_vector_head],
        "listing_vector_head": listing_embedding[:print_vector_head],
    }

    if debug_images:
        payload["images_debug"] = await embedder.debug_image_candidates(listing.images or [])

    if compare_text_only:
        listing_text_only_embedding = await embedder.generate_listing_embedding(
            raw_listing=listing,
            image_urls=[],
        )
        raw_cosine_text = EmbeddingGenerator.cosine_similarity(
            query_embedding,
            listing_text_only_embedding,
        )
        payload["text_only_dim"] = len(listing_text_only_embedding)
        payload["text_only_raw_cosine"] = raw_cosine_text
        payload["text_only_similarity_0_1"] = _to_unit_interval(raw_cosine_text)
        payload["delta_similarity_multimodal_minus_text"] = (
            payload["similarity_0_1"] - payload["text_only_similarity_0_1"]
        )

    if compare_images_only:
        try:
            listing_images_only_embedding = await embedder.generate_images_only_embedding(
                image_urls=listing.images or [],
            )
            raw_cosine_images = EmbeddingGenerator.cosine_similarity(
                query_embedding,
                listing_images_only_embedding,
            )
            payload["images_only_dim"] = len(listing_images_only_embedding)
            payload["images_only_raw_cosine"] = raw_cosine_images
            payload["images_only_similarity_0_1"] = _to_unit_interval(raw_cosine_images)
            payload["delta_similarity_multimodal_minus_images"] = (
                payload["similarity_0_1"] - payload["images_only_similarity_0_1"]
            )
        except Exception as e:
            payload["images_only_error"] = str(e)

    print("\n=== EMBEDDING TEST RESULT ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description="Test rapido de embeddings multimodales")
    parser.add_argument(
        "--query",
        default="Departamento luminoso, idealmente al frente, con buena conectividad a microcentro para ir a la oficina y moderno. Me gustaría que tenga lindos amenities. Si es a estrenar, es un plus.",
        help="Texto de preferencia/query para comparar contra el listing",
    )
    parser.add_argument(
        "--url",
        help="URL de listing real (si no se pasa, usa listing sintetico)",
    )
    parser.add_argument(
        "--source",
        default="auto",
        choices=["auto", "argenprop", "mercadolibre"],
        help="Fuente del scraper cuando se usa --url",
    )
    parser.add_argument(
        "--image-url",
        action="append",
        default=[],
        help="URL de imagen para embedding (puede repetirse). Si se usa con --url, reemplaza las del scraper.",
    )
    parser.add_argument(
        "--description",
        default="",
        help="Descripcion para listing sintetico (sin --url)",
    )
    parser.add_argument(
        "--compare-text-only",
        action="store_true",
        help="Genera embedding adicional solo texto y compara similitud",
    )
    parser.add_argument(
        "--compare-images-only",
        action="store_true",
        help="Genera embedding adicional solo imagenes y compara similitud",
    )
    parser.add_argument(
        "--debug-images",
        action="store_true",
        help="Muestra detalle de seleccion/validacion de imagenes para Gemini embedding",
    )
    parser.add_argument(
        "--debug-images-only",
        action="store_true",
        help="Solo diagnostica imagenes (sin llamar a API de embeddings)",
    )
    parser.add_argument(
        "--print-vector-head",
        type=int,
        default=8,
        help="Cantidad de dimensiones a imprimir del vector (debug)",
    )

    args = parser.parse_args()

    try:
        exit_code = asyncio.run(
            run_test(
                query=args.query,
                url=args.url,
                source=args.source,
                image_urls=args.image_url,
                description=args.description,
                compare_text_only=args.compare_text_only,
                compare_images_only=args.compare_images_only,
                debug_images=args.debug_images,
                debug_images_only=args.debug_images_only,
                print_vector_head=max(0, args.print_vector_head),
            )
        )
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Test de embedding interrumpido por usuario")
        sys.exit(130)
    except Exception as e:
        logger.error("Error fatal en test de embedding", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
