"""Pure parsing of the per-case ambiguity allowances contract.

Product-approved alternatives for golden cases whose expected behavior has
more than one defensible interpretation: an allowance declares acceptable
outcomes and alternative tool sequences without mutating the immutable
golden dataset. The scorecard reports both the strict (golden) and the
acceptable (golden + allowances) rates.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from umbral.application.agent_evals.contracts import (
    KNOWN_OUTCOMES,
    KNOWN_TOOLS,
    AgentEvalsValidationError,
)


@dataclass(frozen=True, slots=True)
class AmbiguityAllowance:
    """One product-approved alternative behavior for a golden case."""

    case_id: str
    acceptable_outcomes: tuple[str, ...]
    alternative_tools: tuple[tuple[str, ...], ...]
    justification: str


def load_allowances(
    path: Path, known_case_ids: frozenset[str] = frozenset()
) -> Mapping[str, AmbiguityAllowance]:
    """Load and validate the ambiguity allowances sidecar from a file path."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise AgentEvalsValidationError(("agent_evals.allowances_required",))
    return parse_allowances(raw, known_case_ids=known_case_ids)


def parse_allowances(
    data: Mapping[str, object], known_case_ids: frozenset[str] = frozenset()
) -> Mapping[str, AmbiguityAllowance]:
    """Parse and validate the allowances document; raises on the first group."""
    errors: list[str] = []
    if data.get("contract_version") != "1":
        errors.append("agent_evals.unsupported_contract_version")
    if data.get("registry_version") != "ambiguity-allowances-v1":
        errors.append("agent_evals.registry_version_required")
    raw_allowances = data.get("allowances")
    if not isinstance(raw_allowances, list):
        errors.append("agent_evals.allowances_required")
        raw_allowances = []
    allowances: list[AmbiguityAllowance] = []
    seen: set[str] = set()
    for raw in raw_allowances:
        if not isinstance(raw, Mapping):
            errors.append("agent_evals.allowance_invalid_shape")
            continue
        case_id = raw.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            errors.append("agent_evals.case_id_required")
            continue
        if known_case_ids and case_id not in known_case_ids:
            errors.append(f"agent_evals.unknown_case:{case_id}")
        if case_id in seen:
            errors.append(f"agent_evals.duplicate_allowance:{case_id}")
        seen.add(case_id)
        raw_outcomes = raw.get("acceptable_outcomes")
        if not isinstance(raw_outcomes, list) or not raw_outcomes:
            errors.append(f"agent_evals.outcomes_required:{case_id}")
            raw_outcomes = []
        for outcome in raw_outcomes:
            if outcome not in KNOWN_OUTCOMES:
                errors.append(f"agent_evals.unknown_outcome:{case_id}:{outcome}")
        raw_tools = raw.get("alternative_tools")
        if not isinstance(raw_tools, list):
            errors.append(f"agent_evals.alternative_tools_invalid:{case_id}")
            raw_tools = []
        alternatives: list[tuple[str, ...]] = []
        for sequence in raw_tools:
            if not isinstance(sequence, list) or not all(
                isinstance(item, str) for item in sequence
            ):
                errors.append(f"agent_evals.tool_sequence_invalid:{case_id}")
                continue
            for tool in sequence:
                if tool not in KNOWN_TOOLS:
                    errors.append(f"agent_evals.unknown_tool:{case_id}:{tool}")
            alternatives.append(tuple(sequence))
        justification = raw.get("justification")
        if not isinstance(justification, str) or not justification:
            errors.append(f"agent_evals.justification_required:{case_id}")
        allowances.append(
            AmbiguityAllowance(
                case_id=case_id,
                acceptable_outcomes=tuple(raw_outcomes),
                alternative_tools=tuple(alternatives),
                justification=str(justification or ""),
            )
        )
    if errors:
        raise AgentEvalsValidationError(tuple(sorted(set(errors))))
    return {allowance.case_id: allowance for allowance in allowances}
