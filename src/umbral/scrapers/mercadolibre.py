"""
Scraper para MercadoLibre Inmuebles (Argentina).

Extrae listings de departamentos en alquiler y venta de CABA.
"""

import re
from typing import Optional
from urllib.parse import urljoin, quote

import structlog
from playwright.async_api import Page

from umbral.models import RawListing, ListingFeatures
from umbral.scrapers.base import BaseScraper

logger = structlog.get_logger()


class MercadoLibreScraper(BaseScraper):
    """
    Scraper específico para MercadoLibre Inmuebles Argentina.

    URLs de ejemplo:
    - Alquiler CABA: https://inmuebles.mercadolibre.com.ar/departamentos/alquiler/capital-federal/
    - Venta Palermo: https://inmuebles.mercadolibre.com.ar/departamentos/venta/palermo/
    """

    SOURCE_NAME = "mercadolibre"
    BASE_URL = "https://inmuebles.mercadolibre.com.ar"

    # Mapeo de barrios a slugs de MercadoLibre
    NEIGHBORHOOD_SLUGS = {
        "Palermo": "palermo",
        "Belgrano": "belgrano",
        "Recoleta": "recoleta",
        "Caballito": "caballito",
        "Almagro": "almagro",
        "Villa Crespo": "villa-crespo",
        "Colegiales": "colegiales",
        "Nuñez": "nunez",
        "Villa Urquiza": "villa-urquiza",
        "Saavedra": "saavedra",
        "Devoto": "villa-devoto",
        "Villa del Parque": "villa-del-parque",
        "Flores": "flores",
        "Floresta": "floresta",
        "Once": "balvanera",  # Once está en Balvanera
        "Balvanera": "balvanera",
        "San Telmo": "san-telmo",
        "La Boca": "la-boca",
        "Barracas": "barracas",
        "Constitución": "constitucion",
        "Monserrat": "monserrat",
        "San Nicolás": "san-nicolas",
        "Retiro": "retiro",
        "Puerto Madero": "puerto-madero",
        "Boedo": "boedo",
        "Parque Patricios": "parque-patricios",
        "Chacarita": "chacarita",
        "Villa Ortúzar": "villa-ortuzar",
        "Paternal": "la-paternal",
        "Agronomía": "agronomia",
        "Parque Chas": "parque-chas",
        "Coghlan": "coghlan",
    }

    def build_search_url(
        self,
        operation_type: str = "alquiler",
        property_type: str = "departamento",
        neighborhood: Optional[str] = None,
        page: int = 1,
    ) -> str:
        """Construye URL de búsqueda para MercadoLibre."""
        # Mapear tipo de propiedad
        property_slug = "departamentos" if property_type == "departamento" else "casas"

        # Construir path base
        if neighborhood and neighborhood in self.NEIGHBORHOOD_SLUGS:
            location = self.NEIGHBORHOOD_SLUGS[neighborhood]
        else:
            location = "capital-federal"

        # URL base
        url = f"{self.BASE_URL}/{property_slug}/{operation_type}/{location}/"

        # Agregar paginación (MercadoLibre usa _Desde_XX)
        if page > 1:
            offset = (page - 1) * 48  # 48 resultados por página
            url += f"_Desde_{offset + 1}"

        return url

    async def get_listing_urls(self, page: Page) -> list[str]:
        """Extrae URLs de listings de la página de resultados."""
        urls = []

        # Debug: ver la URL actual
        current_url = page.url
        logger.info(f"Buscando listings en: {current_url}")

        # Selectores para items de resultado (actualizados 2024)
        selectors = [
            # Selector principal de cards
            ".ui-search-result",
            ".ui-search-layout__item",
            ".andes-card"
            # Alternativo
            "div.ui-search-result__wrapper a.ui-search-link",
            # Cards de galería
            "li.ui-search-layout__item a.ui-search-result__link",
            # Selector más genérico - links que contienen MLA
            "a[href*='/MLA-']",
            # Cards de resultados nuevos
            ".ui-search-layout__item a[href*='inmueble']",
            ".poly-card a",
        ]

        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                logger.info(f"Selector '{selector}': {len(elements)} elementos encontrados")
                
                for element in elements:
                    href = await element.get_attribute("href")
                    if href and "/MLA-" in href:
                        # Limpiar URL de parámetros de tracking
                        clean_url = href.split("#")[0].split("?")[0]
                        if clean_url not in urls:
                            urls.append(clean_url)
                            
                if urls:
                    logger.info(f"Encontradas {len(urls)} URLs con selector: {selector}")
                    break
                    
            except Exception as e:
                logger.warning(f"Error con selector {selector}: {e}")

        # Si no encontramos nada, intentar buscar cualquier link a inmuebles
        if not urls:
            logger.warning("No se encontraron listings con selectores estándar, probando alternativo...")
            all_links = await page.query_selector_all("a")
            for link in all_links:
                href = await link.get_attribute("href")
                if href and "/MLA-" in href and "inmueble" in href.lower():
                    clean_url = href.split("#")[0].split("?")[0]
                    if clean_url not in urls:
                        urls.append(clean_url)
            logger.info(f"Búsqueda alternativa: {len(urls)} URLs encontradas")

        if not urls:
            try:
                title = await page.title()
                body_text = await page.text_content("body") or ""
                body_snippet = body_text.strip().replace("\n", " ")[:300]
                flags = []
                lower = body_text.lower()
                for keyword in ("robot", "captcha", "verific", "blocked", "unusual traffic"):
                    if keyword in lower:
                        flags.append(keyword)
                logger.warning(
                    "Página sin resultados",
                    title=title,
                    snippet=body_snippet,
                    flags=",".join(flags) if flags else "none",
                )
            except Exception as e:
                logger.warning("No se pudo inspeccionar la página", error=str(e))

        return urls

    async def parse_listing(self, page: Page, url: str) -> Optional[RawListing]:
        """Parsea una página de listing de MercadoLibre."""
        try:
            # Extraer ID externo de la URL (MLA-XXXXXXXXX)
            match = re.search(r"MLA-?(\d+)", url)
            if not match:
                logger.warning("No se pudo extraer ID de URL", url=url)
                return None
            external_id = f"MLA-{match.group(1)}"

            # Título
            title = await self._safe_get_text(
                page, "h1.ui-pdp-title", default=""
            )
            if not title:
                title = await self._safe_get_text(
                    page, ".ui-vip-core-title h1", default="Sin título"
                )

            # Precio
            price_data = await self._extract_price(page)

            # Descripción
            description = await self._extract_description(page)

            # Ubicación
            address = await self._safe_get_text(page, ".ui-vip-location__subtitle p.ui-pdp-media__title")
            location_data = await self._extract_location(page)

            # Características
            specs = await self._extract_specifications(page)

            # Imágenes
            images = await self._extract_images(page)

            # Features booleanas
            features = await self._extract_features(page, description)
            
            # Coordenadas
            coordinates = await self._extract_coordinates(page)

            return RawListing(
                external_id=external_id,
                url=url,
                source=self.SOURCE_NAME,
                title=title,
                description=description,
                price=price_data["price"],
                currency=price_data["currency"],
                location=address,
                region=location_data["region"],
                city=location_data["city"],
                neighborhood=location_data["neighborhood"],
                rooms=specs.get("rooms", "1"),
                bathrooms=specs.get("bathrooms", "1"),
                size_total=specs.get("size_total", ""),
                size_covered=specs.get("size_covered", ""),
                age=specs.get("age"),
                disposition=specs.get("disposition"),
                orientation=specs.get("orientation"),
                maintenance_fee=specs.get("maintenance_fee"),
                operation_type=self._detect_operation_type(url),
                images=images,
                coordinates=coordinates,  # MercadoLibre no expone coordenadas fácilmente
                parking_spaces=specs.get("parking", 0),
                features=features,
            )

        except Exception as e:
            logger.error(
                "Error parseando listing de MercadoLibre",
                url=url,
                error=str(e),
            )
            return None

    async def _extract_price(self, page: Page) -> dict:
        """Extrae precio y moneda."""
        result = {"price": "0", "currency": "ARS"}

        # Selector principal de precio
        price_selectors = [
            "span.andes-money-amount__fraction",
            ".ui-pdp-price__second-line span.andes-money-amount__fraction",
            ".price-tag-fraction",
        ]

        for selector in price_selectors:
            price_text = await self._safe_get_text(page, selector)
            if price_text:
                # Limpiar y normalizar
                price_clean = re.sub(r"[^\d]", "", price_text)
                if price_clean:
                    result["price"] = price_clean
                    break

        # Detectar moneda
        currency_selectors = [
            "span.andes-money-amount__currency-symbol",
            ".price-tag-symbol",
        ]

        for selector in currency_selectors:
            currency_text = await self._safe_get_text(page, selector)
            if currency_text:
                if "US" in currency_text or "$" in currency_text and "U" in currency_text:
                    result["currency"] = "USD"
                else:
                    result["currency"] = "ARS"
                break

        # También verificar en el texto completo del precio
        full_price = await self._safe_get_text(page, ".ui-pdp-price__second-line")
        if "dólar" in full_price.lower() or "usd" in full_price.lower():
            result["currency"] = "USD"

        return result

    async def _extract_description(self, page: Page) -> str:
        """Extrae la descripción completa."""
        description_selectors = [
            "p.ui-pdp-description__content",
            ".ui-pdp-description__content",
            ".item-description__text",
        ]

        for selector in description_selectors:
            desc = await self._safe_get_text(page, selector)
            if desc and len(desc) > 50:
                return desc

        return "Sin descripción disponible"

    async def _extract_location(self, page: Page) -> dict:
        """Extrae información de ubicación."""  
        # Buscar en breadcrumbs
        breadcrumb_selectors = [
            "ol.andes-breadcrumb li a.andes-breadcrumb__link"
        ]
        for selector in breadcrumb_selectors:
            breadcrumb_count = await page.locator(selector).count()
            components = []
            for i in range(4, breadcrumb_count):
                breadcrumb = page.locator(selector).nth(i)
                text = await breadcrumb.text_content()
                if text:
                    components.append(text.strip())
                
            if len(components) == 3:
                return {
                    "region": components[0],
                    "city": components[1],
                    "neighborhood": components[2]
                }
            elif len(components) == 2:
                return {
                    "region": components[0],
                    "city": components[0],
                    "neighborhood": components[1]
                }
            
            return None

    async def _extract_specifications(self, page: Page) -> dict:
        """Extrae especificaciones técnicas del inmueble."""
        specs = {}

        # Recolectar texto de múltiples fuentes
        full_text = ""
        
        # 1. Specs destacados (iconos con labels)
        spec_selectors = [
            ".ui-pdp-highlighted-specs-res__icon-label",
            ".ui-pdp-highlighted-specs-res li",
            ".ui-vip-specs__item",
            ".ui-pdp-specs__table tr",
            ".ui-pdp-features__item",
            # Selectores nuevos de MercadoLibre
            "[data-testid='highlighted-specs'] li",
            ".ui-vpp-highlighted-specs li",
            ".andes-table__row",
        ]
        
        for selector in spec_selectors:
            try:
                items = await page.query_selector_all(selector)
                for item in items:
                    text = await item.inner_text()
                    full_text += " " + text.lower()
            except Exception:
                pass

        # 2. También buscar en la descripción
        desc_element = await page.query_selector(".ui-pdp-description__content, .ui-pdp-description")
        if desc_element:
            desc_text = await desc_element.inner_text()
            full_text += " " + desc_text.lower()

        # 3. Buscar en el título
        title_element = await page.query_selector("h1")
        if title_element:
            title_text = await title_element.inner_text()
            full_text += " " + title_text.lower()

        logger.debug(f"Texto para extracción de specs: {full_text[:500]}...")

        # === AMBIENTES ===
        # Patrones comunes: "2 ambientes", "3 amb", "monoambiente", "2 dormitorios"
        rooms_patterns = [
            r"(\d+)\s*amb(?:iente)?s?(?:\b|$)",
            r"(\d+)\s*dormitorio",
            r"(\d+)\s*habitaci[oó]n",
            r"monoambiente",
        ]
        for pattern in rooms_patterns:
            match = re.search(pattern, full_text)
            if match:
                if "monoambiente" in pattern:
                    specs["rooms"] = "1"
                else:
                    specs["rooms"] = match.group(1)
                break
        if "rooms" not in specs:
            specs["rooms"] = "1"

        # === BAÑOS ===
        bath_patterns = [
            r"(\d+)\s*baños?",
            r"(\d+)\s*toilettes?",
        ]
        for pattern in bath_patterns:
            match = re.search(pattern, full_text)
            if match:
                specs["bathrooms"] = match.group(1)
                break

        # === SUPERFICIE ===
        # Buscar superficie total y cubierta
        size_patterns = [
            (r"(\d+(?:[.,]\d+)?)\s*m[²2]\s*(?:total|totales)", "size_total"),
            (r"(\d+(?:[.,]\d+)?)\s*m[²2]\s*(?:cub|cubiertos?)", "size_covered"),
            (r"superficie\s*(?:total)?[:\s]*(\d+(?:[.,]\d+)?)\s*m", "size_total"),
            (r"superficie\s*cubierta[:\s]*(\d+(?:[.,]\d+)?)\s*m", "size_covered"),
        ]
        for pattern, key in size_patterns:
            match = re.search(pattern, full_text)
            if match and key not in specs:
                specs[key] = match.group(1).replace(",", ".")
        
        # Si no encontramos ninguna superficie, buscar cualquier m²
        if "size_total" not in specs:
            any_size = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", full_text)
            if any_size:
                specs["size_total"] = any_size.group(1).replace(",", ".")

        # === ANTIGÜEDAD ===
        age_patterns = [
            r"(\d+)\s*años?\s*(?:de\s*)?antig[üu]edad",
            r"antig[üu]edad[:\s]*(\d+)\s*años?",
            r"(\d+)\s*años?\s*de\s*construido",
        ]
        for pattern in age_patterns:
            match = re.search(pattern, full_text)
            if match:
                specs["age"] = match.group(1)
                break
        
        if "age" not in specs:
            if "a estrenar" in full_text or "estrenar" in full_text or "nuevo" in full_text:
                specs["age"] = "0"

        # === DISPOSICIÓN ===
        if "contrafrente" in full_text or "contra frente" in full_text:
            specs["disposition"] = "contrafrente"
        elif "interno" in full_text:
            specs["disposition"] = "interno"
        elif "lateral" in full_text:
            specs["disposition"] = "lateral"
        elif "frente" in full_text:
            specs["disposition"] = "frente"

        # === ORIENTACIÓN ===
        orientation_patterns = [
            r"orientaci[oó]n[:\s]*(norte|sur|este|oeste|noreste|noroeste|sudeste|sudoeste)",
            r"(norte|sur|este|oeste)\s*(?:luminoso|soleado)?",
        ]
        for pattern in orientation_patterns:
            match = re.search(pattern, full_text)
            if match:
                specs["orientation"] = match.group(1).capitalize()
                break

        # === EXPENSAS ===
        exp_patterns = [
            r"expensas[:\s]*\$?\s*([\d.,]+)",
            r"\$\s*([\d.,]+)\s*(?:de\s*)?expensas",
        ]
        for pattern in exp_patterns:
            match = re.search(pattern, full_text)
            if match:
                specs["maintenance_fee"] = match.group(1).replace(".", "").replace(",", "")
                break

        # === COCHERAS ===
        parking_patterns = [
            r"(\d+)\s*cocheras?",
            r"(\d+)\s*estacionamientos?",
            r"(\d+)\s*garages?",
            r"cochera\s*(?:para\s*)?(\d+)",
        ]
        for pattern in parking_patterns:
            match = re.search(pattern, full_text)
            if match:
                specs["parking"] = int(match.group(1))
                break
        
        if "parking" not in specs:
            if "cochera" in full_text or "garage" in full_text or "estacionamiento" in full_text:
                specs["parking"] = 1

        logger.debug(f"Specs extraídos: {specs}")
        return specs

    async def _extract_images(self, page: Page) -> list[str]:
        """Extrae URLs de imágenes."""
        images = []

        # Selectores de imágenes
        img_selectors = [
            "figure.ui-pdp-gallery__figure img",
            ".ui-pdp-gallery img",
            "img.ui-pdp-image",
        ]

        for selector in img_selectors:
            elements = await page.query_selector_all(selector)
            for element in elements:
                src = await element.get_attribute("src")
                data_src = await element.get_attribute("data-src")
                img_url = data_src or src

                if img_url and "http" in img_url:
                    # Obtener versión de mayor resolución
                    img_url = img_url.replace("-O.webp", "-F.webp")
                    if img_url not in images:
                        images.append(img_url)

            if images:
                break

        return images[:10]  # Máximo 10 imágenes

    async def _extract_features(
        self, page: Page, description: str
    ) -> ListingFeatures:
        """Extrae características booleanas del listing."""
        # Combinar descripción con texto de características
        spec_text = await self._safe_get_text(page, ".ui-pdp-specs")
        amenities_text = await self._safe_get_text(page, ".ui-pdp-highlighted-specs-res")
        full_text = f"{description} {spec_text} {amenities_text}".lower()

        return ListingFeatures(
            is_furnished="amoblado" in full_text or "amueblado" in full_text,
            is_pet_friendly="mascota" in full_text or "pet friendly" in full_text,
            has_security="seguridad" in full_text or "vigilancia" in full_text,
            has_elevator="ascensor" in full_text,
            has_gas="gas natural" in full_text or "gas de red" in full_text,
            has_air_conditioning="aire acondicionado" in full_text or "a/a" in full_text,
            has_heating="calefacción" in full_text or "calefacci" in full_text,
            has_laundry="lavadero" in full_text or "lavarropas" in full_text,
            has_sum="sum" in full_text or "salón de usos múltiples" in full_text,
            has_bbq="parrilla" in full_text or "quincho" in full_text,
            has_pool="pileta" in full_text or "piscina" in full_text,
            has_gym="gimnasio" in full_text or "gym" in full_text,
            has_balcony="balcón" in full_text or "balcon" in full_text,
            has_terrace="terraza" in full_text,
            has_garden="jardín" in full_text or "jardin" in full_text,
            has_patio="patio" in full_text,
        )
    
    async def _extract_coordinates(self, page: Page) -> dict:
        """Extrae coordenadas de la página."""
        try:
            img_element = await page.query_selector(".ui-vip-location__map img.ui-pdp-image")
            if img_element:
                src = await img_element.get_attribute("src")
                if src:
                    # Obtener coordenadas de la URL
                    params = src.split("&")
                    for param in params:
                        if "center" in param:
                            coordinates = param.split("=")[1].split("%2C")
                            return {"lat": float(coordinates[0]), "lng": float(coordinates[1])}
            return None
        except Exception as e:
            logger.error(f"Error extracting coordinates: {str(e)}")
            return None

    def _detect_operation_type(self, url: str) -> str:
        """Detecta si es alquiler o venta desde la URL."""
        if "/alquiler/" in url.lower():
            return "alquiler"
        elif "/venta/" in url.lower():
            return "venta"
        return "alquiler"  # Default
