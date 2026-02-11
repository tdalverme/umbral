"""
Script para preparar propiedades para matching.

Procesa raw_listings pendientes y genera analyzed_listings
normalizados con embedding del texto crudo del scraper.

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
from umbral.analysis import EmbeddingGenerator
from umbral.models import RawListing, ListingFeatures, AnalyzedListing, PropertyScores, InferredFeatures

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
    Prepara listings pendientes para matching.

    Args:
        limit: Máximo de listings a procesar
    """
    settings = get_settings()
    raw_repo = RawListingRepository()
    analyzed_repo = AnalyzedListingRepository()
    embedder = EmbeddingGenerator()
    
    stats = {
        "processed": 0,
        "prepared": 0,
        "embedded": 0,
        "errors": 0,
    }

    logger.info("Iniciando preparacion de listings", limit=limit)

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

            # Preparar listing normalizado SIN analisis por LLM
            logger.info(
                "Preparando listing",
                external_id=raw_listing.external_id,
                title=raw_listing.title[:50],
            )

            try:
                price_original = float(raw_listing.price.replace(".", "").replace(",", "."))
            except ValueError:
                price_original = 0.0

            price_usd = AnalyzedListing.calculate_price_usd(
                price_original,
                raw_listing.currency,
                settings.ars_to_usd_rate,
            )

            try:
                size = float(raw_listing.size_covered or raw_listing.size_total or "0")
            except ValueError:
                size = 0.0

            price_per_m2 = AnalyzedListing.calculate_price_per_m2(price_usd, size)

            try:
                rooms = int(raw_listing.rooms)
            except ValueError:
                rooms = 1

            analyzed_listing = AnalyzedListing(
                raw_listing_id=raw_data["id"],
                external_id=raw_listing.external_id,
                currency_original=raw_listing.currency,
                price_original=price_original,
                price_usd=price_usd,
                price_per_m2_usd=price_per_m2,
                neighborhood=raw_listing.neighborhood,
                rooms=rooms,
                scores=PropertyScores(
                    quietness=0.5,
                    luminosity=0.5,
                    connectivity=0.5,
                    wfh_suitability=0.5,
                    modernity=0.5,
                    green_spaces=0.5,
                ),
                features=InferredFeatures(),
                style_tags=[],
                executive_summary="Resumen personalizado disponible al hacer match.",
                analysis_version=settings.analysis_version,
            )
            stats["prepared"] += 1

            # Guardar en DB
            result = analyzed_repo.create(analyzed_listing)

            if result:
                # Generar embeddings
                try:
                    # Embedding desde datos crudos del scraper
                    embedding = await embedder.generate_listing_embedding(
                        raw_listing=raw_listing,
                    )
                    stats["embedded"] += 1

                    # Guardar embedding principal
                    analyzed_repo.update_embedding(
                        listing_id=result["id"],
                        embedding=embedding,
                    )

                    logger.info(
                        "Listing preparado y embebido",
                        external_id=raw_listing.external_id,
                        neighborhood=analyzed_listing.neighborhood,
                        rooms=analyzed_listing.rooms,
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

    logger.info("Preparacion completada", **stats)
    return stats


def main():
    """Entry point del script."""
    parser = argparse.ArgumentParser(
        description="Prepara propiedades para matching"
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
