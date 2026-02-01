"""
Script para ejecutar el bot de Telegram.

Uso:
    python -m umbral.scripts.run_bot
"""

import sys

import structlog

from umbral.bot import UmbralBot

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


def main():
    """Entry point del bot."""
    logger.info("Iniciando bot de Telegram UMBRAL...")

    try:
        bot = UmbralBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot detenido por usuario")
        sys.exit(0)
    except Exception as e:
        logger.error("Error fatal en bot", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
