"""Parser unit tests for the model price table and derived cost (T007)."""

from __future__ import annotations

import pytest

from umbral.application.agent_evals.contracts import (
    AgentEvalsValidationError,
    ModelCallCostRecord,
)
from umbral.application.agent_evals.price import case_cost, parse_price_table


def _price_table() -> dict[str, object]:
    return {
        "contract_version": "1",
        "registry_version": "price-table-v1",
        "currency": "usd",
        "prices": [
            {
                "model_version": "provider-x-model-y",
                "price_input_per_1k": 0.0005,
                "price_output_per_1k": 0.0015,
            }
        ],
    }


def test_price_table_parses() -> None:
    table = parse_price_table(_price_table())
    entry = table.price_for("provider-x-model-y")
    assert entry is not None
    assert entry.price_input_per_1k == 0.0005
    assert entry.price_output_per_1k == 0.0015


def test_case_cost_derives_from_tokens_and_prices() -> None:
    table = parse_price_table(_price_table())
    cost = case_cost(
        [
            ModelCallCostRecord(
                model_version="provider-x-model-y",
                input_tokens=2000,
                output_tokens=1000,
            )
        ],
        table,
    )
    assert cost == round((2000 * 0.0005 + 1000 * 0.0015) / 1000, 4)


def test_case_cost_ignores_unknown_model() -> None:
    table = parse_price_table(_price_table())
    cost = case_cost(
        [ModelCallCostRecord(model_version="unknown", input_tokens=1000, output_tokens=0)],
        table,
    )
    assert cost == 0.0


def test_price_table_rejects_duplicate_model() -> None:
    data = _price_table()
    data["prices"] = [data["prices"][0], data["prices"][0]]
    with pytest.raises(AgentEvalsValidationError) as excinfo:
        parse_price_table(data)
    assert any(
        "agent_evals.duplicate_model" in code for code in excinfo.value.error_codes
    )


def test_price_table_rejects_negative_price() -> None:
    data = _price_table()
    price = dict(data["prices"][0])
    price["price_input_per_1k"] = -1
    data["prices"] = [price]
    with pytest.raises(AgentEvalsValidationError) as excinfo:
        parse_price_table(data)
    assert any(
        "agent_evals.price_invalid" in code for code in excinfo.value.error_codes
    )
