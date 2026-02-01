"""
Scraper base abstracto.

Define la interfaz común para todos los scrapers de portales inmobiliarios.
"""

import asyncio
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

import structlog
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from umbral.config import get_settings
from umbral.models import RawListing

logger = structlog.get_logger()


@dataclass
class ScraperResult:
    """Resultado de una sesión de scraping."""

    total_listings: int
    new_listings: int
    updated_listings: int
    errors: int
    source: str


class BaseScraper(ABC):
    """
    Clase base abstracta para scrapers de portales inmobiliarios.

    Implementa la lógica común de navegación con Playwright y
    manejo de rate limiting.
    """

    # Nombre del portal (override en subclases)
    SOURCE_NAME: str = "base"

    # URLs base (override en subclases)
    BASE_URL: str = ""
    SEARCH_URL_TEMPLATE: str = ""

    def __init__(self):
        self.settings = get_settings()
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self):
        """Context manager entry: inicializa el browser."""
        await self._init_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: cierra el browser."""
        await self._close_browser()

    async def _init_browser(self):
        """Inicializa Playwright y el browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,  # Headless para producción
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
        )
        # Bloquear recursos innecesarios para acelerar
        await self._context.route(
            "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2}",
            lambda route: route.abort(),
        )
        logger.info("Browser inicializado", source=self.SOURCE_NAME)

    async def _close_browser(self):
        """Cierra el browser y libera recursos."""
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            logger.info("Browser cerrado", source=self.SOURCE_NAME)
        except Exception as e:
            logger.warning(f"Error cerrando browser: {e}")

    async def _new_page(self) -> Page:
        """Crea una nueva página en el contexto."""
        if not self._context:
            raise RuntimeError("Browser no inicializado. Usa 'async with scraper:'")
        return await self._context.new_page()

    async def _random_delay(self):
        """Aplica un delay aleatorio para evitar rate limiting."""
        delay = random.uniform(
            self.settings.scrape_delay_min,
            self.settings.scrape_delay_max,
        )
        await asyncio.sleep(delay)

    async def _safe_get_text(
        self, page: Page, selector: str, default: str = ""
    ) -> str:
        """Obtiene texto de un elemento de forma segura."""
        try:
            element = await page.query_selector(selector)
            if element:
                text = await element.inner_text()
                return text.strip()
        except Exception:
            pass
        return default

    async def _safe_get_attribute(
        self, page: Page, selector: str, attribute: str, default: str = ""
    ) -> str:
        """Obtiene un atributo de un elemento de forma segura."""
        try:
            element = await page.query_selector(selector)
            if element:
                value = await element.get_attribute(attribute)
                return value.strip() if value else default
        except Exception:
            pass
        return default

    @abstractmethod
    def build_search_url(
        self,
        operation_type: str = "alquiler",
        property_type: str = "departamento",
        neighborhood: Optional[str] = None,
        page: int = 1,
    ) -> str:
        """
        Construye la URL de búsqueda para el portal.

        Args:
            operation_type: 'alquiler' o 'venta'
            property_type: 'departamento', 'casa', etc.
            neighborhood: Barrio específico (opcional)
            page: Número de página

        Returns:
            URL completa de búsqueda
        """
        pass

    @abstractmethod
    async def get_listing_urls(self, page: Page) -> list[str]:
        """
        Extrae las URLs de listings de una página de resultados.

        Args:
            page: Página de Playwright con resultados cargados

        Returns:
            Lista de URLs de listings individuales
        """
        pass

    @abstractmethod
    async def parse_listing(self, page: Page, url: str) -> Optional[RawListing]:
        """
        Parsea una página de listing individual.

        Args:
            page: Página de Playwright
            url: URL del listing

        Returns:
            RawListing parseado o None si hay error
        """
        pass

    async def scrape_search_page(
        self, url: str
    ) -> AsyncGenerator[str, None]:
        """
        Scrapea una página de resultados y genera URLs de listings.

        Args:
            url: URL de la página de búsqueda

        Yields:
            URLs de listings individuales
        """
        page = await self._new_page()
        try:
            logger.info(f"Navegando a: {url}")
            
            response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            if response:
                logger.info(f"Respuesta HTTP: {response.status}")
            else:
                logger.warning("No se recibió respuesta HTTP")
            
            # Esperar a que cargue el contenido dinámico
            await page.wait_for_timeout(3000)
            await self._random_delay()

            listing_urls = await self.get_listing_urls(page)
            logger.info(
                "URLs extraídas de página de búsqueda",
                source=self.SOURCE_NAME,
                count=len(listing_urls),
            )

            for listing_url in listing_urls:
                yield listing_url

        except Exception as e:
            logger.error(
                "Error scrapeando página de búsqueda",
                source=self.SOURCE_NAME,
                url=url,
                error=str(e),
            )
            import traceback
            traceback.print_exc()
        finally:
            await page.close()

    async def scrape_listing(self, url: str) -> Optional[RawListing]:
        """
        Scrapea un listing individual.

        Args:
            url: URL del listing

        Returns:
            RawListing parseado o None si hay error
        """
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self._random_delay()

            listing = await self.parse_listing(page, url)
            if listing:
                logger.debug(
                    "Listing parseado",
                    source=self.SOURCE_NAME,
                    external_id=listing.external_id,
                )
            return listing

        except Exception as e:
            logger.error(
                "Error scrapeando listing",
                source=self.SOURCE_NAME,
                url=url,
                error=str(e),
            )
            return None
        finally:
            await page.close()

    async def scrape(
        self,
        operation_type: str = "alquiler",
        property_type: str = "departamento",
        neighborhoods: Optional[list[str]] = None,
        max_pages: Optional[int] = None,
    ) -> AsyncGenerator[RawListing, None]:
        """
        Ejecuta el scraping completo.

        Args:
            operation_type: 'alquiler' o 'venta'
            property_type: Tipo de propiedad
            neighborhoods: Lista de barrios a scrapear (None = todos)
            max_pages: Máximo de páginas por barrio

        Yields:
            RawListing para cada propiedad encontrada
        """
        max_pages = max_pages or self.settings.max_pages_per_run
        neighborhoods = neighborhoods or [None]  # None = búsqueda general

        for neighborhood in neighborhoods:
            logger.info(
                "Iniciando scraping",
                source=self.SOURCE_NAME,
                operation=operation_type,
                neighborhood=neighborhood or "todos",
            )

            for page_num in range(1, max_pages + 1):
                search_url = self.build_search_url(
                    operation_type=operation_type,
                    property_type=property_type,
                    neighborhood=neighborhood,
                    page=page_num,
                )

                listing_count = 0
                async for listing_url in self.scrape_search_page(search_url):
                    listing = await self.scrape_listing(listing_url)
                    if listing:
                        listing_count += 1
                        yield listing

                # Si no hay listings en esta página, terminamos
                if listing_count == 0:
                    logger.info(
                        "No más listings en página",
                        source=self.SOURCE_NAME,
                        page=page_num,
                    )
                    break

                logger.info(
                    "Página completada",
                    source=self.SOURCE_NAME,
                    page=page_num,
                    listings=listing_count,
                )
