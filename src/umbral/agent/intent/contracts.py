"""Pure values and contracts for intent compilation (UM-H4-017, R-01/R-02)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True, slots=True)
class IntentDeclaration:
    """One declared intent with its deterministic allowed-tools policy."""

    name: str
    description: str
    allowed_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IntentContract:
    """The parsed intent schema v3: intents, policy and high-impact keys."""

    registry_version: str
    schema_version: str
    intents: tuple[IntentDeclaration, ...]
    high_impact_keys: tuple[str, ...]
    output_schema: Mapping[str, object]

    def known_intents(self) -> frozenset[str]:
        return frozenset(declaration.name for declaration in self.intents)

    def allowed_tools_for(self, intent: str) -> tuple[str, ...]:
        for declaration in self.intents:
            if declaration.name == intent:
                return declaration.allowed_tools
        return ()


@dataclass(frozen=True, slots=True)
class IntentParameter:
    """An extracted parameter with its confidence."""

    key: str
    value: str
    confidence: float


@dataclass(frozen=True, slots=True)
class IntentContradiction:
    """A requested change that contradicts the current profile snapshot."""

    key: str
    current_value: str
    requested: str


@dataclass(frozen=True, slots=True)
class IntentCompilation:
    """Compiled intent of a message plus the deterministic tool policy."""

    intent: str
    parameters: tuple[IntentParameter, ...]
    high_impact_missing: tuple[str, ...]
    contradictions: tuple[IntentContradiction, ...]
    allowed_tools: tuple[str, ...]


class IntentCompilationError(Exception):
    """Base class for sanitized intent compilation failures."""

    code = "agent.intent_failed"


class IntentCompilationFailed(IntentCompilationError):
    """The model gateway did not produce a valid structured intent."""

    code = "agent.intent_compilation_failed"


class IntentUnclassified(IntentCompilationError):
    """The gateway produced an intent outside the published taxonomy."""

    code = "agent.intent_unclassified"


def parse_intent_contract(data: Mapping[str, object]) -> IntentContract:
    """Parse and validate the machine-checkable intent schema v3."""
    if data.get("registry_version") != "agent-intent-schema-v3":
        raise IntentContractInvalid("registry_version")
    if data.get("schema_version") != "intent-v3":
        raise IntentContractInvalid("schema_version")
    raw_intents = data.get("intents")
    if not isinstance(raw_intents, list):
        raise IntentContractInvalid("intents")
    declarations: list[IntentDeclaration] = []
    for raw in raw_intents:
        if not isinstance(raw, Mapping):
            raise IntentContractInvalid("intent")
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise IntentContractInvalid("intent.name")
        if any(existing.name == name for existing in declarations):
            raise IntentContractInvalid("intent.duplicate")
        raw_tools = raw.get("allowed_tools")
        tools = (
            tuple(cast(str, tool) for tool in raw_tools)
            if isinstance(raw_tools, list)
            and all(isinstance(tool, str) for tool in raw_tools)
            else ()
        )
        declarations.append(
            IntentDeclaration(
                name=name,
                description=_string(raw, "description"),
                allowed_tools=tools,
            )
        )
    raw_keys = data.get("high_impact_keys")
    keys = (
        tuple(cast(str, key) for key in raw_keys)
        if isinstance(raw_keys, list) and all(isinstance(k, str) for k in raw_keys)
        else ()
    )
    output = data.get("output")
    if not isinstance(output, Mapping):
        raise IntentContractInvalid("output")
    return IntentContract(
        registry_version=_string(data, "registry_version"),
        schema_version=_string(data, "schema_version"),
        intents=tuple(declarations),
        high_impact_keys=keys,
        output_schema=output,
    )


class IntentContractInvalid(ValueError):
    """An intent contract file failed structural validation."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"intent_contract_invalid: {reason}")


def _string(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise IntentContractInvalid(f"intent.{key}")
    return value
