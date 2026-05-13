import pytest

from umbral.analysis.listing_analyzer import ListingAnalyzer
from umbral.analysis.llm_providers import LLMResponse
from umbral.models import ListingFeatures, RawListing


class RejectLargePayloadProvider:
    provider_name = "groq"
    model = "groq/compound"

    def __init__(self, max_chars: int):
        self.max_chars = max_chars
        self.calls = []

    async def generate(self, system_prompt, user_prompt, temperature=0.2, max_tokens=4096):
        total_chars = len(system_prompt) + len(user_prompt)
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "total_chars": total_chars,
                "max_tokens": max_tokens,
            }
        )
        if total_chars > self.max_chars:
            raise Exception(
                "Error code: 413 - {'error': {'message': 'Request Entity Too Large', "
                "'type': 'invalid_request_error', 'code': 'request_too_large'}}"
            )
        return LLMResponse(
            text='{"scores":{"quietness":0.5,"luminosity":0.6,"connectivity":0.7,"wfh_suitability":0.6,"modernity":0.5,"green_spaces":0.4},"features":{"is_investment_opportunity":false,"is_family_friendly":false,"has_high_storage_capacity":false,"neighborhood_vibe":"residencial","view_type":"contrafrente"},"style_tags":["luminoso","compacto"],"executive_summary":"Opcion correcta, con datos suficientes para evaluar sin exagerar."}',
            model=self.model,
            provider=self.provider_name,
        )


def _listing():
    long_description = " ".join(["Departamento luminoso cerca del subte con amenities."] * 400)
    return RawListing(
        external_id="ml-long-1",
        url="https://example.test/listing",
        source="mercadolibre",
        title="Departamento de 2 ambientes muy luminoso en Palermo",
        description=long_description,
        price="850",
        currency="USD",
        location="Palermo, CABA",
        neighborhood="Palermo",
        rooms="2",
        bathrooms="1",
        size_total="55",
        size_covered="50",
        maintenance_fee="120000",
        features=ListingFeatures(has_balcony=True, has_elevator=True),
    )


@pytest.mark.asyncio
async def test_listing_analyzer_retries_413_with_ultra_compact_payload():
    provider = RejectLargePayloadProvider(max_chars=2600)
    analyzer = ListingAnalyzer.__new__(ListingAnalyzer)
    analyzer._provider = provider

    result = await analyzer.analyze(_listing())

    assert result.executive_summary.startswith("Opcion correcta")
    assert len(provider.calls) == 2
    assert provider.calls[1]["total_chars"] < provider.calls[0]["total_chars"]
    assert provider.calls[1]["max_tokens"] <= 512
