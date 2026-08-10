"""Pure parsing and validation of the golden conversations dataset contract.

The dataset is a versioned, immutable, product-reviewed contract file
(``contracts/agent-evals/v1/conversations-golden-v1.json``). Validation rejects
malformed cases, unknown families, tools, outcomes or tags, duplicate ids,
incomplete expectations and missing per-family coverage (research R-01/R-02).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from umbral.application.agent_evals.contracts import (
    KNOWN_FAMILIES,
    KNOWN_OUTCOMES,
    KNOWN_TOOLS,
    AgentEvalsValidationError,
    GoldenConversationCase,
    GoldenDataset,
    GoldenExpectation,
    GoldenToolCallExpectation,
    GroundingExpectation,
)

_KNOWN_TAGS: frozenset[str] = frozenset(
    {
        "onboarding",
        "requires_confirmation",
        "interrupts",
        "injection",
        "rejects",
    }
)


def load_golden_dataset(path: Path) -> GoldenDataset:
    """Load and validate the golden conversations dataset from a file path."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise AgentEvalsValidationError(("agent_evals.dataset_required",))
    return parse_golden_dataset(raw)


def parse_golden_dataset(
    data: Mapping[str, object],
    *,
    require_coverage: bool = True,
) -> GoldenDataset:
    """Parse and validate a golden conversations dataset; raises on the first group."""
    errors: list[str] = []
    if data.get("contract_version") != "1":
        errors.append("agent_evals.unsupported_contract_version")
    if data.get("registry_version") != "conversations-golden-v1":
        errors.append("agent_evals.registry_version_required")
    reviewed_by = _required_str(data.get("reviewed_by"), errors, "reviewed_by")
    reviewed_at = _required_str(data.get("reviewed_at"), errors, "reviewed_at")
    min_cases = data.get("min_cases_per_family")
    if min_cases != 3:
        errors.append("agent_evals.min_cases_per_family_required")
    minimum = _as_int(min_cases, 3)
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        errors.append("agent_evals.cases_required")
        raw_cases = []
    cases: list[GoldenConversationCase] = []
    seen_ids: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, Mapping):
            errors.append("agent_evals.case_invalid_shape")
            continue
        case, case_errors = _parse_case(raw)
        if case_errors:
            errors.extend(case_errors)
            continue
        if case.id in seen_ids:
            errors.append(f"agent_evals.duplicate_case:{case.id}")
        seen_ids.add(case.id)
        cases.append(case)
    if errors:
        raise AgentEvalsValidationError(tuple(sorted(set(errors))))
    if require_coverage:
        missing = _missing_family_coverage(tuple(cases), minimum)
        if missing:
            raise AgentEvalsValidationError(
                tuple(
                    sorted(
                        f"agent_evals.missing_coverage:{family}" for family in missing
                    )
                )
            )
    return GoldenDataset(
        contract_version="1",
        registry_version=str(data.get("registry_version") or "conversations-golden-v1"),
        reviewed_by=reviewed_by or "",
        reviewed_at=reviewed_at or "",
        min_cases_per_family=minimum,
        cases=tuple(cases),
    )


def _parse_case(raw: Mapping[str, object]) -> tuple[GoldenConversationCase, list[str]]:
    errors: list[str] = []
    case_id = _required_str(raw.get("id"), errors, "id")
    family = raw.get("family")
    if not isinstance(family, str) or family not in KNOWN_FAMILIES:
        errors.append(f"agent_evals.unknown_family:{family}")
    raw_context = raw.get("context")
    context: Mapping[str, object] = {}
    if isinstance(raw_context, Mapping):
        context = dict(raw_context)
    elif raw_context is not None:
        errors.append("agent_evals.context_invalid_shape")
    raw_turns = raw.get("turns")
    if not isinstance(raw_turns, list) or not raw_turns:
        errors.append("agent_evals.turns_required")
        turns: tuple[str, ...] = ()
    else:
        turns = tuple(str(item) for item in raw_turns)
    raw_expectation = raw.get("expectation")
    if not isinstance(raw_expectation, Mapping):
        errors.append("agent_evals.expectation_required")
        expectation = GoldenExpectation(
            tool_calls=(),
            grounding=GroundingExpectation(
                require_refs=False, min_refs=0, declare_missing=False
            ),
            outcome="failed",
        )
    else:
        expectation, expectation_errors = _parse_expectation(raw_expectation)
        errors.extend(expectation_errors)
    tags = _parse_tags(raw.get("tags"), errors)
    notes = raw.get("notes")
    if notes is not None and not isinstance(notes, str):
        errors.append("agent_evals.notes_invalid")
    return (
        GoldenConversationCase(
            id=case_id,
            family=str(family or ""),
            context=context,
            turns=turns,
            expectation=expectation,
            tags=tags,
            notes=str(notes) if isinstance(notes, str) else None,
        ),
        errors,
    )


def _parse_expectation(
    raw: Mapping[str, object],
) -> tuple[GoldenExpectation, list[str]]:
    errors: list[str] = []
    raw_tool_calls = raw.get("tool_calls")
    tool_calls: list[GoldenToolCallExpectation] = []
    if isinstance(raw_tool_calls, list):
        seen_orders: set[int] = set()
        for item in raw_tool_calls:
            if not isinstance(item, Mapping):
                errors.append("agent_evals.tool_call_invalid_shape")
                continue
            tool = item.get("tool")
            if not isinstance(tool, str) or tool not in KNOWN_TOOLS:
                errors.append(f"agent_evals.unknown_tool:{tool}")
            args = item.get("args")
            if not isinstance(args, Mapping):
                errors.append(f"agent_evals.tool_args_invalid:{tool}")
                args = {}
            requires_confirmation = bool(item.get("requires_confirmation", False))
            order = _as_int(item.get("order"), 0)
            if order <= 0:
                errors.append(f"agent_evals.tool_order_invalid:{tool}")
            if order in seen_orders:
                errors.append(f"agent_evals.duplicate_tool_order:{tool}")
            seen_orders.add(order)
            tool_calls.append(
                GoldenToolCallExpectation(
                    tool=str(tool or ""),
                    args=dict(args),
                    requires_confirmation=requires_confirmation,
                    order=order,
                )
            )
    elif raw_tool_calls is not None:
        errors.append("agent_evals.tool_calls_invalid")
    raw_grounding = raw.get("grounding")
    if not isinstance(raw_grounding, Mapping):
        errors.append("agent_evals.grounding_required")
        grounding = GroundingExpectation(
            require_refs=False, min_refs=0, declare_missing=False
        )
    else:
        grounding = GroundingExpectation(
            require_refs=bool(raw_grounding.get("require_refs", False)),
            min_refs=_as_int(raw_grounding.get("min_refs"), 0) or 0,
            declare_missing=bool(raw_grounding.get("declare_missing", False)),
        )
        if grounding.require_refs and grounding.min_refs < 1:
            errors.append("agent_evals.grounding_min_refs_invalid")
    outcome = raw.get("outcome")
    if not isinstance(outcome, str) or outcome not in KNOWN_OUTCOMES:
        errors.append(f"agent_evals.unknown_outcome:{outcome}")
    tool_calls_sorted = tuple(sorted(tool_calls, key=lambda call: call.order))
    return (
        GoldenExpectation(
            tool_calls=tool_calls_sorted,
            grounding=grounding,
            outcome=outcome,  # type: ignore[arg-type]
        ),
        errors,
    )


def _parse_tags(raw: object, errors: list[str]) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errors.append("agent_evals.tags_invalid")
        return ()
    tags: list[str] = []
    for item in raw:
        if not isinstance(item, str) or item not in _KNOWN_TAGS:
            errors.append(f"agent_evals.unknown_tag:{item}")
            continue
        tags.append(item)
    if len(set(tags)) != len(tags):
        errors.append("agent_evals.duplicate_tag")
    return tuple(tags)


def _missing_family_coverage(
    cases: tuple[GoldenConversationCase, ...], minimum: int
) -> set[str]:
    covered: dict[str, int] = {}
    for case in cases:
        covered[case.family] = covered.get(case.family, 0) + 1
    return {family for family in KNOWN_FAMILIES if covered.get(family, 0) < minimum}


def _required_str(value: object, errors: list[str], field: str) -> str:
    if not isinstance(value, str) or not value:
        errors.append(f"agent_evals.{field}_required")
        return ""
    return value


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return default
