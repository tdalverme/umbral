"""
Script para ejecutar el bot de Telegram.

Uso:
    python -m umbral.scripts.run_bot
"""

import asyncio
import os
import sys

import structlog
from aiohttp import web
from telegram import Update

from umbral.bot import UmbralBot
from umbral.config import get_settings
from umbral.scripts.run_scraper import run_scraper as run_scraper_job

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


async def run_webhook(
    bot: UmbralBot, base_url: str, path: str, listen: str, port: int
):
    application = bot.setup(use_webhook=True)
    settings = get_settings()

    webhook_path = f"/{path.lstrip('/')}"
    webhook_url = f"{base_url.rstrip('/')}{webhook_path}"

    await application.bot.set_webhook(
        url=webhook_url,
        allowed_updates=Update.ALL_TYPES,
    )

    app = web.Application()
    scrape_task: asyncio.Task | None = None

    async def handle_update(request: web.Request) -> web.Response:
        update = Update.de_json(data=await request.json(), bot=application.bot)
        await application.update_queue.put(update)
        return web.Response(text="ok")

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def trigger_scrape(request: web.Request) -> web.Response:
        nonlocal scrape_task

        token = request.headers.get("X-Trigger-Token")
        expected = settings.scrape_trigger_token
        if not expected or token != expected:
            return web.Response(text="forbidden", status=403)

        if scrape_task and not scrape_task.done():
            return web.Response(text="scrape_in_progress", status=409)

        operation = request.query.get("operation", "alquiler").strip()
        if operation not in ("alquiler", "venta"):
            logger.warning(
                "Operación inválida",
                operation=operation,
                query=dict(request.query),
            )
            return web.Response(text=f"invalid_operation:{operation}", status=400)

        def parse_int(value: str | None, default: int | None) -> int | None:
            if value is None or value == "":
                return default
            try:
                return int(value.strip())
            except ValueError:
                return None

        max_pages = parse_int(request.query.get("max_pages"), 5)
        max_listings = parse_int(request.query.get("max_listings"), None)
        if max_pages is None or max_listings is None:
            logger.warning(
                "Límites inválidos",
                max_pages=request.query.get("max_pages"),
                max_listings=request.query.get("max_listings"),
                query=dict(request.query),
            )
            return web.Response(text="invalid_limits", status=400)

        neighborhoods_raw = request.query.get("neighborhoods", "")
        neighborhoods = (
            [n.strip() for n in neighborhoods_raw.split(",") if n.strip()]
            if neighborhoods_raw
            else None
        )

        async def _run_scrape():
            try:
                logger.info(
                    "Scrape trigger recibido",
                    operation=operation,
                    max_pages=max_pages,
                    max_listings=max_listings,
                    neighborhoods=neighborhoods or "todos",
                )
                stats = await run_scraper_job(
                    source="mercadolibre",
                    operation_type=operation,
                    neighborhoods=neighborhoods,
                    max_pages=max_pages,
                    max_listings=max_listings,
                )
                logger.info("Scrape finalizado", **stats)
            except Exception as e:
                logger.error("Scrape falló", error=str(e))

        scrape_task = asyncio.create_task(_run_scrape())
        return web.Response(text="started")

    app.router.add_post(webhook_path, handle_update)
    app.router.add_get("/health", health)
    app.router.add_post("/run-scrape", trigger_scrape)

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
