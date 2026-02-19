"""
Script para ejecutar el scraping de propiedades.

Uso:
    python -m umbral.scripts.run_scraper --source mercadolibre --operation alquiler
    python -m umbral.scripts.run_scraper --neighborhoods Palermo,Belgrano
    python -m umbral.scripts.run_scraper --max-listings 20
"""

import argparse
import asyncio
import logging
import sys
import warnings
from typing import Optional

# Suprimir warnings de cleanup de asyncio en Windows (Python 3.14)
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", message=".*unclosed.*")
warnings.filterwarnings("ignore", message=".*I/O operation on closed pipe.*")

import structlog

from umbral.config import get_settings, CABA_NEIGHBORHOODS
from umbral.database import RawListingRepository
from umbral.scrapers import MercadoLibreScraper, ArgenPropScraper

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


async def run_scraper(
    source: str = "mercadolibre",
    operation_type: str = "alquiler",
    neighborhoods: Optional[list[str]] = None,
    max_pages: int = 5,
    max_listings: Optional[int] = None,
):
    """
    Ejecuta el scraping de propiedades.

    Args:
        source: Portal a scrapear (mercadolibre, zonaprop, argenprop)
        operation_type: alquiler o venta
        neighborhoods: Lista de barrios (None = todos)
        max_pages: Máximo de páginas por barrio
    """
    settings = get_settings()
    repo = RawListingRepository()

    # Seleccionar scraper
    if source == "mercadolibre":
        scraper_class = MercadoLibreScraper
    elif source == "argenprop":
        scraper_class = ArgenPropScraper
    else:
        raise ValueError(f"Scraper no implementado para: {source}")

    # Stats
    stats = {
        "total": 0,
        "new": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
    }

    logger.info(
        "Iniciando scraping",
        source=source,
        operation=operation_type,
        neighborhoods=neighborhoods or "todos",
        max_pages=max_pages,
    )

    async with scraper_class() as scraper:
        async for listing in scraper.scrape(
            operation_type=operation_type,
            neighborhoods=neighborhoods,
            max_pages=max_pages,
            max_listings=max_listings,
        ):
            stats["total"] += 1

            try:
                # Verificar si ya existe por hash
                if repo.exists_by_hash(listing.hash_id):
                    stats["skipped"] += 1
                    logger.debug(
                        "Listing ya existe",
                        external_id=listing.external_id,
                        hash=listing.hash_id,
                    )
                    continue

                # Insertar o actualizar
                result = repo.upsert(listing)
                if result:
                    stats["new"] += 1
                    logger.info(
                        "Listing guardado",
                        external_id=listing.external_id,
                        neighborhood=listing.neighborhood,
                        price=f"{listing.currency} {listing.price}",
                    )

            except Exception as e:
                stats["errors"] += 1
                logger.error(
                    "Error guardando listing",
                    external_id=listing.external_id,
                    error=str(e),
                )

    logger.info("Scraping completado", **stats)
    return stats


def main():
    """Entry point del script."""
    parser = argparse.ArgumentParser(
        description="Scraper de propiedades inmobiliarias"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="mercadolibre",
        choices=["mercadolibre", "zonaprop", "argenprop"],
        help="Portal a scrapear",
    )
    parser.add_argument(
        "--operation",
        type=str,
        default="alquiler",
        choices=["alquiler", "venta"],
        help="Tipo de operación",
    )
    parser.add_argument(
        "--neighborhoods",
        type=str,
        default=None,
        help="Barrios separados por coma (ej: Palermo,Belgrano)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Máximo de páginas por barrio",
    )
    parser.add_argument(
        "--max-listings",
        type=int,
        default=None,
        help="Máximo de listings a procesar (None = sin límite)",
    )

    args = parser.parse_args()

    # Parsear barrios
    neighborhoods = None
    if args.neighborhoods:
        neighborhoods = [n.strip() for n in args.neighborhoods.split(",")]
        # Validar
        for n in neighborhoods:
            if n not in CABA_NEIGHBORHOODS:
                logger.warning(f"Barrio no reconocido: {n}")

    # Ejecutar con manejo de errores mejorado
    try:
        # Crear nuevo event loop explícitamente
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            stats = loop.run_until_complete(
                run_scraper(
                    source=args.source,
                    operation_type=args.operation,
                    neighborhoods=neighborhoods,
                    max_pages=args.max_pages,
                    max_listings=args.max_listings,
                )
            )
            exit_code = 0 if stats["errors"] == 0 else 1
        finally:
            # Cleanup más limpio
            try:
                # Cancelar tareas pendientes
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                    try:
                        loop.run_until_complete(task)
                    except asyncio.CancelledError:
                        pass
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            finally:
                loop.close()
        
        # Suprimir errores de cleanup al salir
        import os
        os._exit(exit_code)
            
    except KeyboardInterrupt:
        logger.info("Scraping interrumpido por usuario")
        import os
        os._exit(130)
    except Exception as e:
        import traceback
        logger.error("Error fatal en scraper", error=str(e))
        traceback.print_exc()
        import os
        os._exit(1)


if __name__ == "__main__":
    main()
