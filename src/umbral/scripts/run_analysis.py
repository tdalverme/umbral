"""
Script para analizar propiedades con IA.

Procesa raw_listings pendientes y genera analyzed_listings
con scores cualitativos y embeddings.

Uso:
    python -m umbral.scripts.run_analysis
    python -m umbral.scripts.run_analysis --limit 50
"""

import argparse
import asyncio
import sys
import warnings

import structlog

# Suprimir warnings de cleanup de asyncio en Windows
warnings.filterwarnings("ignore", category=ResourceWarning, message=".*unclosed transport.*")

from umbral.config import get_settings
from umbral.database import RawListingRepository, AnalyzedListingRepository
from umbral.analysis import ListingAnalyzer, EmbeddingGenerator
from umbral.models import RawListing, ListingFeatures

# Configurar logging
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


async def run_analysis(limit: int = 100):
    """
    Analiza listings pendientes con Gemini.

    Args:
        limit: Máximo de listings a procesar
    """
    settings = get_settings()
    raw_repo = RawListingRepository()
    analyzed_repo = AnalyzedListingRepository()
    analyzer = ListingAnalyzer()  # Usa settings.llm_provider automáticamente
    embedder = EmbeddingGenerator()
    
    logger.info(
        "Usando proveedor LLM",
        provider=settings.llm_provider,
        model=settings.groq_model if settings.llm_provider == "groq" else settings.gemini_model,
    )

    stats = {
        "processed": 0,
        "analyzed": 0,
        "embedded": 0,
        "vibe_embedded": 0,
        "errors": 0,
    }

    logger.info("Iniciando análisis de listings", limit=limit)

    # Obtener listings no analizados
    pending = raw_repo.get_unanalyzed(limit=limit)
    logger.info(f"Listings pendientes de análisis: {len(pending)}")

    for raw_data in pending:
        stats["processed"] += 1

        try:
            # Reconstruir RawListing desde DB
            raw_listing = RawListing(
                external_id=raw_data["external_id"],
                url=raw_data["url"],
                source=raw_data["source"],
                title=raw_data["title"],
                description=raw_data["description"],
                price=raw_data["price"],
                currency=raw_data["currency"],
                location=raw_data["location"],
                region=raw_data.get("region", "CABA"),
                city=raw_data.get("city", "Buenos Aires"),
                neighborhood=raw_data["neighborhood"],
                rooms=raw_data["rooms"],
                bathrooms=raw_data.get("bathrooms", "1"),
                size_total=raw_data.get("size_total", ""),
                size_covered=raw_data.get("size_covered", ""),
                age=raw_data.get("age"),
                disposition=raw_data.get("disposition"),
                orientation=raw_data.get("orientation"),
                maintenance_fee=raw_data.get("maintenance_fee"),
                operation_type=raw_data.get("operation_type"),
                images=raw_data.get("images", []),
                coordinates=raw_data.get("coordinates"),
                parking_spaces=raw_data.get("parking_spaces"),
                features=ListingFeatures(**raw_data.get("features", {})),
            )

            # Analizar con Gemini
            logger.info(
                "Analizando listing",
                external_id=raw_listing.external_id,
                title=raw_listing.title[:50],
            )

            analysis = await analyzer.analyze(raw_listing)
            stats["analyzed"] += 1

            # Crear AnalyzedListing
            analyzed_listing = analyzer.create_analyzed_listing(
                raw_listing=raw_listing,
                raw_listing_id=raw_data["id"],
                analysis=analysis,
            )

            # Guardar en DB
            result = analyzed_repo.create(analyzed_listing)

            if result:
                # Generar embeddings
                try:
                    # Embedding completo del listing
                    embedding = await embedder.generate_listing_embedding(
                        raw_listing=raw_listing,
                        analyzed_listing=analyzed_listing,
                    )
                    stats["embedded"] += 1

                    # Vibe embedding (solo executive_summary + style_tags)
                    vibe_embedding = await embedder.generate_vibe_embedding(
                        executive_summary=analyzed_listing.executive_summary,
                        style_tags=analyzed_listing.style_tags,
                    )
                    stats["vibe_embedded"] += 1

                    # Guardar ambos en una sola operación
                    analyzed_repo.update_embeddings(
                        listing_id=result["id"],
                        embedding=embedding,
                        vibe_embedding=vibe_embedding,
                    )

                    logger.info(
                        "Listing analizado y embebido",
                        external_id=raw_listing.external_id,
                        quietness=analysis.scores.quietness,
                        luminosity=analysis.scores.luminosity,
                        style_tags=analyzed_listing.style_tags[:3],
                    )

                except Exception as e:
                    logger.error(
                        "Error generando embeddings",
                        external_id=raw_listing.external_id,
                        error=str(e),
                    )

            # Pequeña pausa para no exceder rate limits
            await asyncio.sleep(1)

        except Exception as e:
            stats["errors"] += 1
            logger.error(
                "Error analizando listing",
                external_id=raw_data.get("external_id"),
                error=str(e),
            )

    logger.info("Análisis completado", **stats)
    return stats


def main():
    """Entry point del script."""
    parser = argparse.ArgumentParser(
        description="Analiza propiedades con IA"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Máximo de listings a procesar",
    )

    args = parser.parse_args()

    try:
        stats = asyncio.run(run_analysis(limit=args.limit))
        sys.exit(0 if stats["errors"] == 0 else 1)
    except KeyboardInterrupt:
        logger.info("Análisis interrumpido por usuario")
        sys.exit(130)
    except Exception as e:
        logger.error("Error fatal en análisis", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
