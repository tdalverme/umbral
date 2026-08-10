"""Pure parsing of the model price table and derived cost computation.

Cost is derived, never stored (research R-05): ``case_cost`` computes the cost
of a model-call sequence from recorded token usage against the price table of
the evaluated release. Recomputable and auditable.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from umbral.application.agent_evals.contracts import (
    AgentEvalsValidationError,
    ModelCallCostRecord,
    PriceTable,
    PriceTableEntry,
)


def load_price_table(path: Path) -> PriceTable:
    """Load and validate the price table from a file path."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AgentEvalsValidationError(("agent_evals.price_table_required",))
    return parse_price_table(raw)


def parse_price_table(data: dict[str, object]) -> PriceTable:
    """Parse and validate a price table document; raises on the first group."""
    errors: list[str] = []
    if data.get("contract_version") != "1":
        errors.append("agent_evals.unsupported_contract_version")
    if data.get("registry_version") != "price-table-v1":
        errors.append("agent_evals.registry_version_required")
    currency = data.get("currency")
    if not isinstance(currency, str) or not currency:
        errors.append("agent_evals.currency_required")
    raw_prices = data.get("prices")
    if not isinstance(raw_prices, list) or not raw_prices:
        errors.append("agent_evals.prices_required")
        raw_prices = []
    entries: list[PriceTableEntry] = []
    seen_models: set[str] = set()
    for item in raw_prices:
        if not isinstance(item, dict):
            errors.append("agent_evals.price_invalid_shape")
            continue
        model_version = item.get("model_version")
        if not isinstance(model_version, str) or not model_version:
            errors.append("agent_evals.model_version_required")
            continue
        if model_version in seen_models:
            errors.append(f"agent_evals.duplicate_model:{model_version}")
        seen_models.add(model_version)
        price_input = _as_float(item.get("price_input_per_1k"), -1.0)
        price_output = _as_float(item.get("price_output_per_1k"), -1.0)
        if price_input < 0 or price_output < 0:
            errors.append(f"agent_evals.price_invalid:{model_version}")
        entries.append(
            PriceTableEntry(
                model_version=model_version,
                price_input_per_1k=price_input,
                price_output_per_1k=price_output,
            )
        )
    if errors:
        raise AgentEvalsValidationError(tuple(sorted(set(errors))))
    return PriceTable(
        contract_version="1",
        registry_version="price-table-v1",
        currency=str(currency or "usd"),
        entries=tuple(entries),
    )


def case_cost(calls: Sequence[ModelCallCostRecord], table: PriceTable) -> float:
    """Compute the USD cost of a model-call sequence against a price table."""
    total = 0.0
    for call in calls:
        entry = table.price_for(call.model_version)
        if entry is None:
            continue
        total += (
            call.input_tokens * entry.price_input_per_1k
            + call.output_tokens * entry.price_output_per_1k
        ) / 1000.0
    return round(total, 4)


def _as_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default
