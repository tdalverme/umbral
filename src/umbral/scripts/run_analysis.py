"""
Script para preparar propiedades para matching.

Procesa raw_listings pendientes y genera embeddings multimodales
(texto + imágenes principales cuando están disponibles).

Uso:
    python -m umbral.scripts.run_analysis
    python -m umbral.scripts.run_analysis --limit 50
"""

import argparse
import asyncio
import logging
import sys
import warnings

import structlog

# Suprimir warnings de cleanup de asyncio en Windows
warnings.filterwarnings("ignore", category=ResourceWarning, message=".*unclosed transport.*")

from umbral.database import AnalyzedListingRepository, RawListingRepository, UrbanSignalRepository
from umbral.analysis import EmbeddingGenerator, ListingAnalyzer
from umbral.config import get_settings
from umbral.models import RawListing, ListingFeatures
from umbral.quality import evaluate_listing_quality

# Configurar logging
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


async def run_analysis(limit: int = 100):
    """
    Prepara listings pendientes para matching.

    Args:
        limit: Máximo de listings a procesar
    """
    raw_repo = RawListingRepository()
    analyzed_repo = AnalyzedListingRepository()
    urban_repo = UrbanSignalRepository()
    analyzer = ListingAnalyzer()
    embedder = EmbeddingGenerator()
    
    stats = {
        "processed": 0,
        "enriched": 0,
        "embedded": 0,
        "urban_signals": 0,
        "errors": 0,
    }

    logger.info("Iniciando preparacion de listings", limit=limit)

    pending = raw_repo.get_recent(limit=limit)
    logger.info(f"Listings candidatos a enrichment: {len(pending)}")

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

            logger.info(
                "Preparando listing",
                external_id=raw_listing.external_id,
                title=raw_listing.title[:50],
            )

            existing = analyzed_repo.get_by_raw_listing_id(raw_data["id"])
            if existing and existing.get("embedding_vector") and existing.get("vibe_embedding"):
                logger.debug("Listing ya enriquecido", raw_listing_id=raw_data["id"])
                continue

            quality = evaluate_listing_quality(raw_listing)
            if not quality.accepted:
                logger.info(
                    "Listing salteado por quality gate en enrichment",
                    external_id=raw_listing.external_id,
                    quality=quality.score,
                    reason=quality.reason,
                )
                continue

            analysis = await analyzer.analyze(raw_listing)
            analyzed_listing = analyzer.create_analyzed_listing(
                raw_listing=raw_listing,
                raw_listing_id=raw_data["id"],
                analysis=analysis,
            )
            analyzed_data = analyzed_listing.to_db_dict()
            analyzed_data["quality_score"] = quality.score
            analyzed_data["quality_reasons"] = {
                "reasons": quality.reasons,
                "penalties": quality.penalties,
                "tags": quality.tags,
            }

            if existing:
                saved = existing
            else:
                saved = analyzed_repo.create_from_dict(analyzed_data)
                stats["enriched"] += 1

            try:
                signal_row = urban_repo.compute_for_listing({**analyzed_data, "id": saved["id"]})
                if signal_row:
                    stats["urban_signals"] += 1
            except Exception as e:
                logger.warning(
                    "No se pudieron calcular senales urbanas",
                    external_id=raw_listing.external_id,
                    error=str(e),
                )

            try:
                embedding = await embedder.generate_listing_embedding(
                    raw_listing=raw_listing,
                    analyzed_listing=analyzed_listing,
                )
                vibe_embedding = await embedder.generate_vibe_embedding(
                    executive_summary=analyzed_listing.executive_summary,
                    style_tags=analyzed_listing.style_tags,
                )
                updated = analyzed_repo.update_embeddings(
                    listing_id=saved["id"],
                    embedding=embedding,
                    vibe_embedding=vibe_embedding,
                )
                raw_repo.update_embedding(raw_data["id"], embedding)
                if updated:
                    stats["embedded"] += 1
                    logger.info(
                        "Listing embebido",
                        external_id=raw_listing.external_id,
                        neighborhood=raw_listing.neighborhood,
                        rooms=raw_listing.rooms,
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
