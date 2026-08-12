"""Pure, versioned canonical preference vocabulary (chat -> concepts).

The LLM never picks ``concept_key`` or ``polarity``: it expresses the natural
phrase and this module maps it deterministically to the published catalog
(constitution II). Phrases without a match raise ``PreferenceUnknownConcept``;
structural problems in the contract raise ``PreferenceVocabularyInvalid``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PreferenceIntent:
    """Resolved canonical preference: concept, polarity and optional value."""

    concept_key: str
    polarity: str
    value: str | None
    requires_value: bool = False


@dataclass(frozen=True, slots=True)
class PreferenceVocabularyEntry:
    """One published entry: the natural aliases and their canonical intent."""

    aliases: tuple[str, ...]
    intent: PreferenceIntent


@dataclass(frozen=True, slots=True)
class PreferenceVocabularySpec:
    registry_version: str
    schema_version: str
    entries: tuple[PreferenceVocabularyEntry, ...]
    unsupported_notes: Mapping[str, str]
    _alias_to_intent: Mapping[str, PreferenceIntent]

    def resolve(self, phrase: str) -> PreferenceIntent:
        """Resolve a natural phrase to its canonical preference.

        Matching is case-insensitive, whitespace-normalized and alias-exact
        (the intent compiler already extracts the canonical phrase); unknown
        phrases are rejected, never guessed.
        """
        key = _alias_key(phrase)
        intent = self._alias_to_intent.get(key)
        if intent is None:
            raise PreferenceUnknownConcept(phrase)
        return intent


class PreferenceVocabularyError(Exception):
    """Base class for sanitized preference vocabulary failures."""

    code = "preference.error"


class PreferenceUnknownConcept(PreferenceVocabularyError):
    """The natural phrase has no published canonical mapping."""

    code = "preference.unknown_concept"

    def __init__(self, phrase: str) -> None:
        self.phrase = phrase
        super().__init__(f"no canonical preference for: {phrase}")


class PreferenceVocabularyInvalid(ValueError):
    """A vocabulary contract file failed structural validation."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"preferences_vocabulary_invalid: {reason}")


def parse_preference_vocabulary(
    data: Mapping[str, object],
) -> PreferenceVocabularySpec:
    if data.get("registry_version") != "preferences-vocabulary-v1":
        raise PreferenceVocabularyInvalid("registry_version")
    if data.get("schema_version") != "preferences-v1":
        raise PreferenceVocabularyInvalid("schema_version")
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise PreferenceVocabularyInvalid("entries")
    entries: list[PreferenceVocabularyEntry] = []
    alias_to_intent: dict[str, PreferenceIntent] = {}
    for raw in raw_entries:
        if not isinstance(raw, Mapping):
            raise PreferenceVocabularyInvalid("entry")
        concept_key = raw.get("concept_key")
        polarity = raw.get("polarity")
        if not isinstance(concept_key, str) or not concept_key:
            raise PreferenceVocabularyInvalid("entry.concept_key")
        if polarity not in {"positive", "negative"}:
            raise PreferenceVocabularyInvalid("entry.polarity")
        value = raw.get("value")
        if value is not None and not isinstance(value, str):
            raise PreferenceVocabularyInvalid("entry.value")
        requires_value = raw.get("requires_value", False)
        if not isinstance(requires_value, bool):
            raise PreferenceVocabularyInvalid("entry.requires_value")
        raw_aliases = raw.get("aliases")
        if not isinstance(raw_aliases, list) or not raw_aliases:
            raise PreferenceVocabularyInvalid("entry.aliases")
        aliases = tuple(
            _alias_key(alias)
            for alias in raw_aliases
            if isinstance(alias, str) and alias.strip()
        )
        if len(aliases) != len(raw_aliases):
            raise PreferenceVocabularyInvalid("entry.aliases")
        intent = PreferenceIntent(
            concept_key=concept_key,
            polarity=polarity,
            value=value if isinstance(value, str) else None,
            requires_value=requires_value,
        )
        for alias in aliases:
            if alias in alias_to_intent:
                raise PreferenceVocabularyInvalid("entry.aliases.duplicate")
            alias_to_intent[alias] = intent
        entries.append(
            PreferenceVocabularyEntry(aliases=aliases, intent=intent)
        )
    unsupported = data.get("unsupported_notes")
    notes: Mapping[str, str] = {}
    if isinstance(unsupported, Mapping):
        notes = {str(key): str(item) for key, item in unsupported.items()}
    return PreferenceVocabularySpec(
        registry_version=str(data["registry_version"]),
        schema_version=str(data["schema_version"]),
        entries=tuple(entries),
        unsupported_notes=notes,
        _alias_to_intent=dict(alias_to_intent),
    )


def _alias_key(phrase: str) -> str:
    return " ".join(phrase.strip().lower().split())
