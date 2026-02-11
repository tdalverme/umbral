"""
Script simple para testear scraping de una URL puntual.

Uso:
    python -m umbral.scripts.test_scrape_url --url "https://www.argenprop.com/..."
    python -m umbral.scripts.test_scrape_url --url "https://inmuebles.mercadolibre.com.ar/..." --source mercadolibre
"""

import argparse
import asyncio
import json
import sys
import warnings
from urllib.parse import urlparse

import structlog

from umbral.scrapers import (
    ArgenPropScraper,
    MercadoLibreScraper,
    KeywordAmenitiesDetector,
)

# Suprimir warnings ruidosos de asyncio/Playwright en Windows
warnings.filterwarnings("ignore", category=ResourceWarning)
warnings.filterwarnings("ignore", message=".*unclosed.*")

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


def _print_detector_debug(payload: dict):
    detector = KeywordAmenitiesDetector()
    title = payload.get("title", "") or ""
    description = payload.get("description", "") or ""
    text = f"{title}. {description}".strip()
    if not text:
        print("\n=== DETECTOR DEBUG ===")
        print("Sin texto para analizar.")
        return

    detected = detector.detect_features_with_evidence(text)
    parking = detector.detect_parking_with_evidence(text)
    final_features = (payload.get("features") or {}).copy()

    print("\n=== DETECTOR DEBUG ===")
    matched_any = False
    for feature, info in detected.items():
        if not info.get("value"):
            continue
        matched_any = True
        final_value = final_features.get(feature)
        print(
            f"- {feature}: matched=True, final_rawlisting={final_value}, "
            f"pattern={info.get('matched_pattern')}, sentence={info.get('matched_sentence')}"
        )

    if not matched_any:
        print("- No hubo matches por texto para amenities booleanas.")

    print(
        f"- parking_spaces: detected={parking.get('value')}, "
        f"final_rawlisting={payload.get('parking_spaces')}, "
        f"pattern={parking.get('matched_pattern')}, sentence={parking.get('matched_sentence')}"
    )


async def run_test(url: str, source: str = "auto", debug_detector: bool = False) -> int:
    selected_source = _detect_source_from_url(url) if source == "auto" else source
    logger.info("Iniciando test de scraping", url=url, source=selected_source)

    scraper = _build_scraper(selected_source)

    async with scraper:
        listing = await scraper.scrape_listing(url)

    if not listing:
        logger.error("No se pudo parsear el listing", url=url, source=selected_source)
        return 1

    payload = listing.model_dump()
    logger.info(
        "RawListing parseado",
        source=selected_source,
        external_id=payload.get("external_id"),
        neighborhood=payload.get("neighborhood"),
    )

    print("\n=== RAW LISTING ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if debug_detector:
        _print_detector_debug(payload)

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Testea scraping de una URL puntual y muestra RawListing"
    )
    parser.add_argument(
        "--url",
        required=True,
        help="URL completa del anuncio a scrapear",
    )
    parser.add_argument(
        "--source",
        default="auto",
        choices=["auto", "argenprop", "mercadolibre"],
        help="Fuente del scraper (auto detecta por dominio)",
    )
    parser.add_argument(
        "--debug-detector",
        action="store_true",
        help="Muestra evidencia de patrones detectados por fallback de amenities",
    )

    args = parser.parse_args()

    try:
        exit_code = asyncio.run(
            run_test(
                url=args.url,
                source=args.source,
                debug_detector=args.debug_detector,
            )
        )
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Test interrumpido por usuario")
        sys.exit(130)
    except Exception as e:
        logger.error("Error fatal en test de scraping", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
