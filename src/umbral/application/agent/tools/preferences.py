"""Pure, versioned canonical preference vocabulary (chat -> concepts).

The LLM never picks ``concept_key`` or ``polarity``: it expresses the natural
phrase and this module maps it deterministically to the published catalog
(constitution II). Phrases without a match raise ``PreferenceUnknownConcept``;
structural problems in the contract raise ``PreferenceVocabularyInvalid``.
"""

from __future__ import annotations

import json
import logging
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_PREFERENCES_VOCABULARY_PATH = (
    Path(__file__).resolve().parents[5]
    / "contracts"
    / "criteria"
    / "v1"
    / "preferences-vocabulary-v1.json"
)


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

        Matching is case-insensitive and whitespace-normalized. An exact alias
        match wins; otherwise the longest alias embedded in the phrase is used
        (the intent compiler often passes the whole predicate, e.g. "depto
        luminoso" or "quiero un depto cerca de un cafe"). Unknown phrases are
        still rejected, never guessed.
        """
        key = _alias_key(phrase)
        intent = self._alias_to_intent.get(key)
        if intent is None:
            intent = self._resolve_embedded(key)
        if intent is None:
            # Log registry snapshot for debugging (preview) — no PII, only phrase y catálogo
            available = sorted({e.intent.concept_key for e in self.entries})
            logger.warning(
                "preference.unknown_concept phrase=%r normalized=%r available=%s entries=%d",
                phrase,
                key,
                available,
                len(self.entries),
            )
            raise PreferenceUnknownConcept(phrase)
        return intent

    def _resolve_embedded(self, key: str) -> PreferenceIntent | None:
        """Return the intent for the longest alias that appears in ``key``."""
        if not key:
            return None
        for alias, intent in sorted(
            self._alias_to_intent.items(),
            key=lambda item: (-len(item[0]), item[0]),
        ):
            if len(alias) >= 2 and alias in key:
                return intent
        return None


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


def load_preference_vocabulary(
    path: Path | None = None,
) -> PreferenceVocabularySpec:
    """Load the legacy tool vocabulary at the application boundary."""
    source = path or _PREFERENCES_VOCABULARY_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_preference_vocabulary(data)


def _alias_key(phrase: str) -> str:
    normalized = unicodedata.normalize("NFD", phrase.strip().casefold())
    without_marks = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return " ".join(without_marks.split())
