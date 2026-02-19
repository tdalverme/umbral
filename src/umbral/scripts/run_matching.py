"""
Script para ejecutar el ciclo de matching y notificaciones.

Busca matches entre listings y usuarios activos,
y envía notificaciones por Telegram.

Uso:
    python -m umbral.scripts.run_matching
"""

import asyncio
import logging
import sys
import warnings

import structlog

# Suprimir warnings de cleanup de asyncio en Windows
warnings.filterwarnings("ignore", category=ResourceWarning, message=".*unclosed transport.*")

from umbral.matching import MatchingEngine
from umbral.config import get_settings

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


async def run_matching():
    """Ejecuta el ciclo de matching."""
    engine = MatchingEngine()
    stats = await engine.run_matching_cycle()
    return stats


def main():
    """Entry point del script."""
    logger.info("Iniciando ciclo de matching...")

    try:
        stats = asyncio.run(run_matching())

        logger.info(
            "Matching completado",
            users=stats.get("users_processed", 0),
            matches=stats.get("matches_found", 0),
            notifications=stats.get("notifications_sent", 0),
        )

        sys.exit(0 if stats.get("errors", 0) == 0 else 1)

    except KeyboardInterrupt:
        logger.info("Matching interrumpido por usuario")
        sys.exit(130)
    except Exception as e:
        logger.error("Error fatal en matching", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
