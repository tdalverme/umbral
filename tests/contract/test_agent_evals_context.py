"""Conformance of the per-case conversation context sidecar contract."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.agent_evals.context import load_conversation_contexts
from umbral.application.agent_evals.golden import load_golden_dataset

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts" / "agent-evals" / "v1"
GOLDEN_PATH = CONTRACTS / "conversations-golden-v1.json"
CONTEXT_PATH = CONTRACTS / "conversation-context-v1.json"

_OBJECT_TOOLS = frozenset({"explain_match", "compare_listings", "record_feedback"})


def test_context_document_is_valid_json() -> None:
    raw = json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))
    assert raw["registry_version"] == "conversation-context-v1"
    assert isinstance(raw["contexts"], list)


def test_context_cases_exist_in_the_golden_dataset() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    known = frozenset(case.id for case in dataset.cases)
    contexts = load_conversation_contexts(CONTEXT_PATH, known_case_ids=known)
    assert contexts


def test_every_object_reference_case_declares_context() -> None:
    """Cases whose tools need listing references must declare the context
    the product would provide via the message context field (UM-H4-025)."""
    dataset = load_golden_dataset(GOLDEN_PATH)
    known = frozenset(case.id for case in dataset.cases)
    contexts = load_conversation_contexts(CONTEXT_PATH, known_case_ids=known)
    for case in dataset.cases:
        tools = {call.tool for call in case.expectation.tool_calls}
        if tools & _OBJECT_TOOLS:
            assert case.id in contexts, (
                f"{case.id} needs context for {sorted(tools & _OBJECT_TOOLS)}"
            )


def test_context_entities_match_the_chat_contract() -> None:
    contexts = load_conversation_contexts(CONTEXT_PATH)
    for context in contexts.values():
        assert context.entity in {"listing", "comparison"}
        if context.entity == "comparison":
            assert context.listing_ids
