"""Unit tests for the manual ZonaProp import generator."""

from __future__ import annotations

import httpx

from umbral.ops.import_zonaprop import (
    Card,
    _CardParser,
    _parse_price,
    build_parser,
    fetch,
    map_card,
    parse_detail_html,
)

_CARD_HTML = """
<div class="postingCardLayout-module__posting-card-layout"
     data-qa="posting PROPERTY"
     data-id="59717897" data-posting-type="PROPERTY"
     data-to-posting="/propiedades/clasificado/alclapin-depto-test-59717897.html?n_pg=1">
  <div class="inner">
    <img src="https://imgar.zonapropcdn.com/avisos/1/00/59/71/78/97/360x266/2068003734.jpg"/>
    <h2 class="postingPrices-module__price"
        data-qa="POSTING_CARD_PRICE">USD 1.350</h2>
    <h2 class="postingPrices-module__expenses"
        data-qa="expensas">$ 350.000 Expensas</h2>
    <h3 class="postingMainFeatures-module__posting-main-features-block"
        data-qa="POSTING_CARD_FEATURES">
      <span>80 m&sup2; tot.</span><span>2 amb.</span><span>1 dorm.</span>
    </h3>
    <h4 class="postingLocations-module__location-address">
      Soldado de la Independencia al 400</h4>
    <h4 class="postingLocations-module__location-text"
        data-qa="POSTING_CARD_LOCATION">Las Ca&ntilde;itas, Palermo</h4>
    <h2 class="postingCard-module__posting-description"
        data-qa="POSTING_CARD_DESCRIPTION">
      <a href="/propiedades/clasificado/alclapin-depto-test-59717897.html">
        Departamento luminoso con balc&oacute;n.</a>
    </h2>
  </div>
</div>
"""

_DETAIL_HTML = """
<script>
const mapLatOf =  "LTM0LjYxNDIyMzc5OTk5OTk5Nw==";
const mapLngOf =  "LTU4LjM2MjQ4OTY5OTk5OTk5Nw==";
</script>
<ul id="section-icon-features-property" class="section-icon-features-property">
  <li class="icon-feature"><i class="icon-stotal"></i>82 m² tot.</li>
  <li class="icon-feature"><i class="icon-scubierta"></i>72 m² cub.</li>
  <li class="icon-feature"><i class="icon-ambiente"></i>2 amb.</li>
  <li class="icon-feature"><i class="icon-dormitorio"></i>1 dorm.</li>
  <li class="icon-feature"><i class="icon-bano"></i>1 baño</li>
  <li class="icon-feature"><i class="icon-cochera"></i>1 coch.</li>
  <li class="icon-feature"><i class="icon-toilete"></i>1 toilette</li>
  <li class="icon-feature"><i class="icon-antiguedad"></i>3 años</li>
  <li class="icon-feature"><i class="icon-disposicion"></i>Frente</li>
  <li class="icon-feature"><i class="icon-orientacion"></i>SE</li>
</ul>
<h1 class="title-property">Departamento en Puerto Madero</h1>
<div id="longDescription">Descripción completa.<br>Con balcón.</div>
<span class="generalFeaturesProperty-module__description-text___123">Gimnasio</span>
<span class="generalFeaturesProperty-module__description-text___123">Parrilla</span>
<img src="https://imgar.zonapropcdn.com/avisos/detail.jpg" />
"""


def _parse(card_html: str = _CARD_HTML) -> Card:
    parser = _CardParser()
    parser.feed(card_html)
    assert len(parser.cards) == 1
    return parser.cards[0]


def test_parser_extracts_card_fields() -> None:
    card = _parse()
    assert card.external_id == "59717897"
    assert card.url == (
        "https://www.zonaprop.com.ar/propiedades/clasificado/"
        "alclapin-depto-test-59717897.html"
    )
    assert card.price_text == "USD 1.350"
    assert card.expenses_text == "$ 350.000 Expensas"
    assert card.features == ["80 m² tot.", "2 amb.", "1 dorm."]
    assert card.address_text == "Soldado de la Independencia al 400"
    assert card.neighborhood_text == "Las Cañitas, Palermo"
    assert card.description == "Departamento luminoso con balcón."
    assert card.media_urls == [
        "https://imgar.zonapropcdn.com/avisos/1/00/59/71/78/97/360x266/2068003734.jpg"
    ]


def test_parser_skips_cards_without_id() -> None:
    parser = _CardParser()
    parser.feed(
        '<div data-qa="posting PROPERTY">'
        '<h2 data-qa="POSTING_CARD_PRICE">USD 1</h2></div>'
    )
    assert parser.cards == []


def test_map_card_full_record() -> None:
    mapped = map_card(_parse(), search_url="https://www.zonaprop.com.ar/departamentos-alquiler-palermo.html")
    assert mapped is not None
    assert mapped["external_id"] == "zonaprop-59717897"
    assert mapped["operation"] == "rental"
    assert mapped["property_type"] == "apartment"
    assert mapped["price"] == 1350.0
    assert mapped["currency"] == "USD"
    assert mapped["address_text"] == "Soldado de la Independencia al 400"
    assert mapped["neighborhood"] == "Las Cañitas"
    assert mapped["rooms"] == 2
    assert mapped["bedrooms"] == 1
    assert mapped["surface_m2"] == 80.0
    assert mapped["expenses"] == 350000.0
    description = mapped["description"]
    url = mapped["url"]
    media_urls = mapped["media_urls"]
    assert isinstance(description, str) and description.startswith(
        "Departamento luminoso"
    )
    assert isinstance(url, str) and url.endswith(
        "alclapin-depto-test-59717897.html"
    )
    assert isinstance(media_urls, list) and len(media_urls) == 1


def test_map_card_falls_back_to_search_url_type() -> None:
    card = Card(
        external_id="123",
        url="https://www.zonaprop.com.ar/propiedades/clasificado/alclapin-vista-unica-123.html",
        price_text="USD 1.000",
    )
    mapped = map_card(card, search_url="https://www.zonaprop.com.ar/casas-alquiler-palermo.html")
    assert mapped is not None
    assert mapped["property_type"] == "house"


def test_map_card_requires_price() -> None:
    card = Card(
        external_id="124",
        url="https://www.zonaprop.com.ar/propiedades/clasificado/x-124.html",
    )
    assert map_card(card) is None


def test_parse_price_currencies() -> None:
    assert _parse_price("USD 1.350") == ("USD", 1350.0)
    assert _parse_price("$ 900.000") == ("ARS", 900000.0)
    assert _parse_price("") == (None, None)


def test_parse_detail_extracts_coordinates_and_supported_features() -> None:
    detail = parse_detail_html(_DETAIL_HTML)

    assert detail.latitude == -34.6142238
    assert detail.longitude == -58.3624897
    assert detail.surface_m2 == 82.0
    assert detail.rooms == 2
    assert detail.bedrooms == 1
    assert detail.description == "Descripción completa.\nCon balcón."
    assert detail.amenities == ("Gimnasio", "Parrilla")
    assert detail.media_urls == ("https://imgar.zonapropcdn.com/avisos/detail.jpg",)


def test_parse_detail_extracts_all_structured_listing_attributes() -> None:
    detail = parse_detail_html(_DETAIL_HTML)

    assert detail.title == "Departamento en Puerto Madero"
    assert detail.surface_covered_m2 == 72.0
    assert detail.bathrooms == 1.0
    assert detail.toilettes == 1.0
    assert detail.parking_spaces == 1.0
    assert detail.age_years == 3.0
    assert detail.disposition == "Frente"
    assert detail.orientation == "SE"


def test_map_card_merges_detail_values_without_losing_card_values() -> None:
    card = _parse()
    detail = parse_detail_html(_DETAIL_HTML)

    mapped = map_card(
        card,
        search_url="https://www.zonaprop.com.ar/departamentos-alquiler-palermo.html",
        detail=detail,
    )

    assert mapped is not None
    assert mapped["latitude"] == -34.6142238
    assert mapped["longitude"] == -58.3624897
    assert mapped["surface_m2"] == 82.0
    assert mapped["surface_covered_m2"] == 72.0
    assert mapped["bathrooms"] == 1.0
    assert mapped["toilettes"] == 1.0
    assert mapped["parking_spaces"] == 1.0
    assert mapped["age_years"] == 3.0
    assert mapped["disposition"] == "Frente"
    assert mapped["orientation"] == "SE"
    assert mapped["title"] == "Departamento en Puerto Madero"
    assert mapped["description"] == "Descripción completa.\nCon balcón."
    assert mapped["amenities"] == ["Gimnasio", "Parrilla"]
    assert mapped["media_urls"] == [
        "https://imgar.zonapropcdn.com/avisos/detail.jpg"
    ]


def test_fetch_enriches_cards_with_detail_loader() -> None:
    def search_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_CARD_HTML, request=request)

    detail_urls: list[str] = []

    def detail_loader(url: str) -> str:
        detail_urls.append(url)
        return _DETAIL_HTML

    with httpx.Client(transport=httpx.MockTransport(search_handler)) as client:
        records, skipped, invalid = fetch(
            client,
            url="https://www.zonaprop.com.ar/departamentos-alquiler-palermo.html",
            max_items=1,
            detail_loader=detail_loader,
        )

    assert skipped == 0
    assert invalid == 0
    assert detail_urls == [
        "https://www.zonaprop.com.ar/propiedades/clasificado/"
        "alclapin-depto-test-59717897.html"
    ]
    assert records[0]["latitude"] == -34.6142238
    assert records[0]["longitude"] == -58.3624897


def test_cli_enables_detail_mode() -> None:
    args = build_parser().parse_args(
        [
            "fetch",
            "--url",
            "https://www.zonaprop.com.ar/departamentos-alquiler-palermo.html",
            "--details",
        ]
    )

    assert args.details is True
