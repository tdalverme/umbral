import asyncio

from umbral.models import RawListing
from umbral.scrapers.argenprop import ArgenPropScraper
from umbral.scrapers.base import BaseScraper
from umbral.scrapers.mercadolibre import MercadoLibreScraper


def _listing(operation_type: str) -> RawListing:
    return RawListing(
        external_id="test-1",
        url="https://example.com/listing",
        source="test",
        title="Departamento de prueba",
        description="Descripcion suficientemente larga para un listing de prueba",
        price="100000",
        currency="USD",
        location="Belgrano",
        neighborhood="Belgrano",
        rooms="2",
        operation_type=operation_type,
    )


class FakeScraper(BaseScraper):
    SOURCE_NAME = "fake"

    def __init__(self):
        super().__init__()
        self.requested_operation_types = []

    def build_search_url(
        self,
        operation_type: str = "alquiler",
        property_type: str = "departamento",
        neighborhood: str | None = None,
        page: int = 1,
    ) -> str:
        self.requested_operation_types.append(operation_type)
        return "https://example.com/search"

    async def get_listing_urls(self, page):
        return []

    async def parse_listing(self, page, url: str):
        return _listing("alquiler")

    async def scrape_search_page(self, url: str):
        yield "https://example.com/listing"

    async def scrape_listing(self, url: str):
        return _listing("alquiler")


class FakeArgenPropPage:
    async def get_attribute(self, selector: str, attribute: str):
        return None

    async def title(self):
        return ""

    async def query_selector(self, selector: str):
        return None


def test_mercadolibre_detects_operation_from_listing_slug():
    scraper = MercadoLibreScraper()

    sale_url = (
        "https://departamento.mercadolibre.com.ar/"
        "MLA-3278269424-edificio-en-venta-en-belgrano"
    )
    rent_url = (
        "https://departamento.mercadolibre.com.ar/"
        "MLA-3278269424-departamento-en-alquiler-en-palermo"
    )

    assert scraper._detect_operation_type(sale_url) == "venta"
    assert scraper._detect_operation_type(rent_url) == "alquiler"


def test_argenprop_prefers_operation_from_listing_url_over_title():
    scraper = ArgenPropScraper()
    page = FakeArgenPropPage()

    operation_type = asyncio.run(
        scraper._detect_operation_type(
            page,
            title="DEPARTAMENTO DE 2 AMBIENTES EN VENTA UBICADO EN BELGRANO",
            url="https://www.argenprop.com/departamento-en-alquiler-en-belgrano-2-ambientes--19445034",
        )
    )

    assert operation_type == "alquiler"


def test_base_scraper_enforces_requested_operation_type_on_results():
    scraper = FakeScraper()

    async def collect():
        return [
            listing
            async for listing in scraper.scrape(
                operation_type="venta",
                neighborhoods=["Belgrano"],
                max_pages=1,
                max_listings=1,
            )
        ]

    listings = asyncio.run(collect())

    assert scraper.requested_operation_types == ["venta"]
    assert listings[0].operation_type == "venta"
