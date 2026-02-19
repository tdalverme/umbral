"""
Script para ejecutar el bot de Telegram.

Uso:
    python -m umbral.scripts.run_bot
"""

import asyncio
import logging
import os
import sys

import structlog
from aiohttp import web
from telegram import Update

from umbral.bot import UmbralBot
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


async def run_webhook(bot: UmbralBot, base_url: str, path: str, listen: str, port: int):
    application = bot.setup(use_webhook=True)

    webhook_path = f"/{path.lstrip('/')}"
    webhook_url = f"{base_url.rstrip('/')}{webhook_path}"

    await application.bot.set_webhook(
        url=webhook_url,
        allowed_updates=Update.ALL_TYPES,
    )

    app = web.Application()

    async def handle_update(request: web.Request) -> web.Response:
        update = Update.de_json(data=await request.json(), bot=application.bot)
        await application.update_queue.put(update)
        return web.Response(text="ok")

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    app.router.add_post(webhook_path, handle_update)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=listen, port=port)

    try:
        async with application:
            await application.start()
            await site.start()
            logger.info(
                "Webhook activo",
                webhook_url=webhook_url,
                health_path="/health",
                listen=listen,
                port=port,
            )
            await asyncio.Event().wait()
    finally:
        await runner.cleanup()


def main():
    """Entry point del bot."""
    logger.info("Iniciando bot de Telegram UMBRAL...")

    try:
        settings = get_settings()
        bot = UmbralBot()
        base_url = settings.telegram_webhook_url or os.getenv("RENDER_EXTERNAL_URL")
        if base_url:
            webhook_path = settings.telegram_webhook_path
            listen = settings.telegram_webhook_listen
            port = int(os.getenv("PORT", "10000"))
            asyncio.run(
                run_webhook(
                    bot=bot,
                    base_url=base_url,
                    path=webhook_path,
                    listen=listen,
                    port=port,
                )
            )
        else:
            bot.run()
    except KeyboardInterrupt:
        logger.info("Bot detenido por usuario")
        sys.exit(0)
    except Exception as e:
        logger.error("Error fatal en bot", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
