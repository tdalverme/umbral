"""Loads the published preference vocabulary contract."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.agent.tools.preferences import (
    PreferenceVocabularySpec,
    parse_preference_vocabulary,
)

_PREFERENCES_VOCABULARY_PATH = (
    Path(__file__).resolve().parents[5]
    / "contracts"
    / "criteria"
    / "v1"
    / "preferences-vocabulary-v1.json"
)


def load_preference_vocabulary(
    path: Path | None = None,
) -> PreferenceVocabularySpec:
    source = path or _PREFERENCES_VOCABULARY_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_preference_vocabulary(data)
