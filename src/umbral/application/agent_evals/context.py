"""Pure parsing of the per-case conversation context contract.

The golden conversations assume product state (which listing the user is
viewing, which listings are being compared) that the chat receives via the
message ``context`` field (UM-H4-025). This sidecar declares that state per
case so the real-provider evals exercise the same context the product
provides; it is versioned and validated against the golden dataset but kept
separate from the immutable conversations contract.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from umbral.application.agent_evals.contracts import AgentEvalsValidationError

_ENTITIES: frozenset[str] = frozenset({"listing", "comparison"})


@dataclass(frozen=True, slots=True)
class ConversationContext:
    """Declared product context of one golden conversation case."""

    case_id: str
    entity: str
    id: str
    listing_ids: tuple[str, ...] = ()


def load_conversation_contexts(
    path: Path, known_case_ids: frozenset[str] = frozenset()
) -> Mapping[str, ConversationContext]:
    """Load and validate the conversation context sidecar from a file path."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise AgentEvalsValidationError(("agent_evals.context_required",))
    return parse_conversation_contexts(raw, known_case_ids=known_case_ids)


def parse_conversation_contexts(
    data: Mapping[str, object], known_case_ids: frozenset[str] = frozenset()
) -> Mapping[str, ConversationContext]:
    """Parse and validate the context document; raises on the first group."""
    errors: list[str] = []
    if data.get("contract_version") != "1":
        errors.append("agent_evals.unsupported_contract_version")
    if data.get("registry_version") != "conversation-context-v1":
        errors.append("agent_evals.registry_version_required")
    raw_contexts = data.get("contexts")
    if not isinstance(raw_contexts, list):
        errors.append("agent_evals.contexts_required")
        raw_contexts = []
    contexts: list[ConversationContext] = []
    seen: set[str] = set()
    for raw in raw_contexts:
        if not isinstance(raw, Mapping):
            errors.append("agent_evals.context_invalid_shape")
            continue
        case_id = raw.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            errors.append("agent_evals.case_id_required")
            continue
        if known_case_ids and case_id not in known_case_ids:
            errors.append(f"agent_evals.unknown_case:{case_id}")
        if case_id in seen:
            errors.append(f"agent_evals.duplicate_context:{case_id}")
        seen.add(case_id)
        entity = raw.get("entity")
        if entity not in _ENTITIES:
            errors.append(f"agent_evals.unknown_context_entity:{entity}")
        object_id = raw.get("id")
        if not isinstance(object_id, str):
            errors.append("agent_evals.context_id_required")
        else:
            try:
                UUID(object_id)
            except ValueError:
                errors.append(f"agent_evals.context_id_invalid:{case_id}")
        listing_ids: list[str] = []
        raw_ids = raw.get("listing_ids")
        if raw_ids is not None:
            if not isinstance(raw_ids, list) or not all(
                isinstance(item, str) for item in raw_ids
            ):
                errors.append(f"agent_evals.listing_ids_invalid:{case_id}")
            else:
                for item in raw_ids:
                    try:
                        UUID(item)
                    except ValueError:
                        errors.append(f"agent_evals.listing_id_invalid:{case_id}")
                        break
                listing_ids = list(raw_ids)
        contexts.append(
            ConversationContext(
                case_id=case_id,
                entity=str(entity),
                id=str(object_id or ""),
                listing_ids=tuple(listing_ids),
            )
        )
    if errors:
        raise AgentEvalsValidationError(tuple(sorted(set(errors))))
    return {context.case_id: context for context in contexts}
