"""
Scraper para ArgenProp Inmuebles (Argentina).

Extrae listings de departamentos en alquiler y venta de CABA.
"""

import re
import unicodedata
from typing import Optional
from urllib.parse import urljoin

import structlog
from playwright.async_api import Page

from umbral.models import RawListing, ListingFeatures
from umbral.scrapers.base import BaseScraper

logger = structlog.get_logger()


class ArgenPropScraper(BaseScraper):
    """
    Scraper específico para ArgenProp.

    URLs de ejemplo:
    - Alquiler CABA: https://www.argenprop.com/departamentos/alquiler/capital-federal
    - Venta Palermo: https://www.argenprop.com/departamentos/venta/palermo
    """

    SOURCE_NAME = "argenprop"
    BASE_URL = "https://www.argenprop.com"

    PROPERTY_TYPE_SLUGS = {
        "departamento": "departamentos",
        "casa": "casas",
        "ph": "ph",
    }

    def _slugify(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\s+", "-", ascii_text.strip().lower())

    def build_search_url(
        self,
        operation_type: str = "alquiler",
        property_type: str = "departamento",
        neighborhood: Optional[str] = None,
        page: int = 1,
    ) -> str:
        """Construye URL de búsqueda para ArgenProp."""
        property_slug = self.PROPERTY_TYPE_SLUGS.get(property_type, "departamentos")
        location = self._slugify(neighborhood) if neighborhood else "capital-federal"
        url = f"{self.BASE_URL}/{property_slug}/{operation_type}/{location}"
        if page > 1:
            url = f"{url}?pagina-{page}"
        return url

    async def get_listing_urls(self, page: Page) -> list[str]:
        """Extrae URLs de listings de la página de resultados."""
        urls: list[str] = []

        selectors = [
            ".listing__item a.card",
            "a.card",
            "a[href*='/propiedades/']",
        ]

        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                logger.info(f"Selector '{selector}': {len(elements)} elementos encontrados")
                for element in elements:
                    href = await element.get_attribute("href")
                    if href:
                        clean_url = href.split("#")[0].split("?")[0]
                        full_url = urljoin(self.BASE_URL, clean_url)
                        if full_url not in urls:
                            urls.append(full_url)
                if urls:
                    break
            except Exception as e:
                logger.warning(f"Error con selector {selector}: {e}")

        return urls

    async def parse_listing(self, page: Page, url: str) -> Optional[RawListing]:
        """Parsea una página de listing de ArgenProp."""
        try:
            external_id = self._extract_id_from_url(url)
            if not external_id:
                logger.warning("No se pudo extraer ID de URL", url=url)
                return None

            title = await self._safe_get_text(
                page, "h2.section-description--title", default=""
            )
            if not title:
                title = await self._safe_get_text(page, ".titlebar__title", default="")
            if not title:
                title = await self._safe_get_text(page, "h1", default="Sin título")

            price_text = await self._safe_get_text(page, "p.titlebar__price", default="")
            price, currency = self._parse_price(price_text)

            description = await self._safe_get_text(
                page, ".section-description--content", default=""
            )
            if not description:
                description = await self._safe_get_text(page, ".section-description", default="")
            if not description:
                description = "Sin descripción disponible"

            address = await self._safe_get_text(page, "h2.titlebar__address", default="")
            location_data = await self._extract_location(page)

            specs, features = await self._extract_features(page)

            images = await self._extract_images(page)
            coordinates = await self._extract_coordinates(page)

            operation_type = await self._detect_operation_type(page, title, url)
            features, inferred_parking = self.enrich_features_from_text(
                features=features,
                title=title,
                description=description,
            )

            parking_spaces = specs.get("parking_spaces")
            if parking_spaces is None and inferred_parking is not None:
                parking_spaces = inferred_parking

            return RawListing(
                external_id=external_id,
                url=url,
                source=self.SOURCE_NAME,
                title=title,
                description=description,
                price=price,
                currency=currency,
                location=address or location_data.get("full", "CABA"),
                region=location_data.get("region", "CABA"),
                city=location_data.get("city", "Buenos Aires"),
                neighborhood=location_data.get("neighborhood", "CABA"),
                rooms=specs.get("rooms", "1"),
                bathrooms=specs.get("bathrooms", "1"),
                size_total=specs.get("size_total", ""),
                size_covered=specs.get("size_covered", ""),
                age=specs.get("age"),
                disposition=specs.get("disposition"),
                orientation=specs.get("orientation"),
                maintenance_fee=specs.get("maintenance_fee"),
                operation_type=operation_type,
                images=images,
                coordinates=coordinates,
                parking_spaces=parking_spaces,
                features=features,
            )

        except Exception as e:
            logger.error(
                "Error parseando listing de ArgenProp",
                url=url,
                error=str(e),
            )
            return None

    def _extract_id_from_url(self, url: str) -> Optional[str]:
        match = re.search(r"--(\d+)$", url)
        if match:
            return match.group(1)
        return None

    def _parse_price(self, price_text: str) -> tuple[str, str]:
        if not price_text:
            return "0", "ARS"
        currency = "USD" if re.search(r"US\$|U\$S|USD", price_text) else "ARS"
        numeric_part = re.sub(r"[^\d]", "", price_text)
        return (numeric_part or "0"), currency

    async def _extract_location(self, page: Page) -> dict:
        location_text = await self._safe_get_text(page, "p.location-container", default="")
        location_text = location_text.replace("  ", " ").strip()
        parts = [p.strip() for p in location_text.split(",") if p.strip()]

        data = {"full": location_text}
        if len(parts) >= 3:
            data.update(
                {
                    "neighborhood": parts[0],
                    "city": parts[1],
                    "region": parts[2],
                }
            )
        elif len(parts) == 2:
            data.update(
                {
                    "neighborhood": parts[0],
                    "city": parts[1],
                    "region": parts[1],
                }
            )
        return data

    async def _extract_features(self, page: Page) -> tuple[dict, ListingFeatures]:
        specs: dict = {}
        features = ListingFeatures()

        # Características principales (property-main-features)
        main_items = await page.query_selector_all(".property-main-features li")
        for item in main_items:
            title_attr = (await item.get_attribute("title") or "").lower()
            strong = await item.query_selector("p.strong")
            value_text = (await strong.text_content() or "").lower() if strong else ""
            combined = f"{title_attr} {value_text}".replace("\n", " ").strip()

            if "sup. cubierta" in combined:
                match = re.search(r"(\d+)", combined)
                if match:
                    specs["size_covered"] = match.group(1)
                    continue
            if "antiguedad" in combined:
                if "a estrenar" in combined:
                    specs["age"] = "0"
                    continue
                match = re.search(r"(\d+)", combined)
                if match:
                    specs["age"] = match.group(1)
                    continue
            if "bañ" in combined:
                match = re.search(r"(\d+)", combined)
                if match:
                    specs["bathrooms"] = match.group(1)
                    continue
            if "ambiente" in combined:
                match = re.search(r"(\d+)", combined)
                if match:
                    specs["rooms"] = match.group(1)
                    continue
            if "disposici" in combined:
                if value_text:
                    specs["disposition"] = value_text.strip()
                    continue
            if "orientaci" in combined:
                if value_text:
                    specs["orientation"] = value_text.strip()
                    continue

        # Superficie (section-superficie)
        surface_items = await page.query_selector_all("#section-superficie li")
        for item in surface_items:
            label = await item.query_selector("p")
            strong = await item.query_selector("strong")
            label_text = (await label.text_content() or "").lower() if label else ""
            value_text = (await strong.text_content() or "").lower() if strong else ""
            combined = f"{label_text} {value_text}".replace("\n", " ").strip()

            if "sup. cubierta" in combined and "size_covered" not in specs:
                match = re.search(r"(\d+)", combined)
                if match:
                    specs["size_covered"] = match.group(1)
            if "sup. total" in combined and "size_total" not in specs:
                match = re.search(r"(\d+)", combined)
                if match:
                    specs["size_total"] = match.group(1)

        elements = await page.query_selector_all(".property-features li, li.property-features-item")
        for element in elements:
            label = (await element.query_selector("p") or await element.query_selector("span"))
            strong = await element.query_selector("strong")
            label_text = (await label.text_content() or "") if label else ""
            value_text = (await strong.text_content() or "") if strong else ""

            raw_text = f"{label_text} {value_text}".strip()
            if not raw_text:
                # Fallback para ítems de lista con texto plano (sin estructura interna)
                raw_text = (await element.inner_text() or "").strip()

            text = raw_text.lower().replace("\n", " ").strip()
            text_normalized = (
                unicodedata.normalize("NFKD", text)
                .encode("ascii", "ignore")
                .decode("ascii")
            )

            if "cant. ambientes" in text or "cant ambientes" in text:
                match = re.search(r"(\d+)", text)
                if match:
                    specs["rooms"] = match.group(1)
                    continue
            if "cant. baños" in text or "cant ban" in text:
                match = re.search(r"(\d+)", text)
                if match:
                    specs["bathrooms"] = match.group(1)
                    continue
            if "antiguedad" in text_normalized:
                match = re.search(r"(\d+)", text)
                if match:
                    specs["age"] = match.group(1)
                    continue
            if "disposicion" in text_normalized:
                if value_text:
                    specs["disposition"] = value_text.strip()
                    continue
            if "orientacion" in text_normalized:
                if value_text:
                    specs["orientation"] = value_text.strip()
                    continue
            if "expensas" in text:
                if value_text:
                    specs["maintenance_fee"] = value_text.strip()
                    continue

            if "ambiente" in text:
                match = re.search(r"(\d+)\s*amb", text)
                if match:
                    specs["rooms"] = match.group(1)
                elif "monoambiente" in text:
                    specs["rooms"] = "1"
            if "baño" in text or "bano" in text_normalized:
                match = re.search(r"(\d+)\s*bañ", text)
                if match:
                    specs["bathrooms"] = match.group(1)
            if "sup" in text or "m²" in text:
                match = re.search(r"(\d+)\s*m", text)
                if match and "size_total" not in specs:
                    specs["size_total"] = match.group(1)
            if "cochera" in text:
                specs["parking_spaces"] = 1
            if "ascensor" in text:
                features.has_elevator = True
            if "balcon" in text_normalized:
                features.has_balcony = True
            if "terraza" in text or "solarium" in text:
                features.has_terrace = True
            if "patio" in text:
                features.has_patio = True
            if "jardin" in text_normalized:
                features.has_garden = True
            if "parrilla" in text:
                features.has_bbq = True
            if "pileta" in text:
                features.has_pool = True
            if "gimnasio" in text:
                features.has_gym = True
            if "lavadero" in text:
                features.has_laundry = True
            if "aire acondicionado" in text:
                features.has_air_conditioning = True
            if "gas natural" in text:
                features.has_gas = True
            if "calefaccion" in text_normalized:
                features.has_heating = True
            if "sum" in text or "quincho" in text:
                features.has_sum = True
            if "mascotas" in text:
                features.is_pet_friendly = True
            if "amoblado" in text:
                features.is_furnished = True

        maintenance_fee = await self._safe_get_text(page, "p.titlebar__expenses", default="")
        if maintenance_fee:
            specs["maintenance_fee"] = maintenance_fee

        return specs, features

    async def _extract_images(self, page: Page) -> list[str]:
        images: list[str] = []
        selectors = [
            "ul.gallery-content img",
            ".gallery-content img",
            "img[itemprop='image']",
        ]
        for selector in selectors:
            elements = await page.query_selector_all(selector)
            for element in elements:
                for attr in ("data-src", "src"):
                    url = await element.get_attribute(attr)
                    if url and url.startswith("http") and url not in images:
                        images.append(url.split("?")[0])
                        break
            if images:
                break
        if not images:
            elements = await page.query_selector_all("[data-open-gallery][style]")
            for element in elements:
                style = await element.get_attribute("style") or ""
                matches = re.findall(r"url\((https?://[^)]+)\)", style)
                for match in matches:
                    clean = match.split("?")[0]
                    if clean not in images:
                        images.append(clean)
                if images:
                    break
        if not images:
            og_image = await page.get_attribute("meta[property='og:image']", "content")
            if og_image:
                images.append(og_image)
        return images

    async def _extract_coordinates(self, page: Page) -> Optional[dict]:
        map_element = await page.query_selector(".map-container .leaflet-container")
        if not map_element:
            return None
        lat = await map_element.get_attribute("data-latitude")
        lng = await map_element.get_attribute("data-longitude")
        if lat and lng:
            try:
                return {"lat": float(lat.replace(",", ".")), "lng": float(lng.replace(",", "."))}
            except Exception:
                return None
        return None

    async def _detect_operation_type(self, page: Page, title: str, url: str) -> str:
        title_lower = (title or "").lower()
        url_lower = (url or "").lower()

        if "venta" in title_lower or "/venta/" in url_lower or "-en-venta-" in url_lower:
            return "venta"
        if "alquiler" in title_lower or "/alquiler/" in url_lower or "-en-alquiler-" in url_lower:
            return "alquiler"

        og_title = await page.get_attribute("meta[property='og:title']", "content")
        og_title_lower = (og_title or "").lower()
        if "venta" in og_title_lower:
            return "venta"
        if "alquiler" in og_title_lower:
            return "alquiler"

        page_title = await page.title()
        page_title_lower = (page_title or "").lower()
        if "venta" in page_title_lower:
            return "venta"
        if "alquiler" in page_title_lower:
            return "alquiler"

        titlebar = await self._safe_get_text(page, ".titlebar__title", default="")
        titlebar_lower = titlebar.lower()
        if "venta" in titlebar_lower:
            return "venta"
        if "alquiler" in titlebar_lower:
            return "alquiler"

        return "alquiler"
