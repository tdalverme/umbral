"""Pure extraction goldens: per-concept labeled cases that gate publication.

Rules run the real deterministic rule against the case input; models and
urban concepts are gated structurally (the published schema covers the
expected values) because the harness never calls the provider. The gate
fails closed: malformed documents raise instead of being skipped.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ExtractionGoldenCase:
    """One labeled case: the permitted input projection and expected value."""

    input: Mapping[str, object]
    expected: object


@dataclass(frozen=True, slots=True)
class ExtractionGolden:
    """The golden gate of one concept: cases plus the minimum accuracy."""

    concept_key: str
    source: str
    accuracy_threshold: float
    cases: tuple[ExtractionGoldenCase, ...] = field(default_factory=tuple)

    def is_sufficient(self, accuracy: float) -> bool:
        return accuracy >= self.accuracy_threshold


@dataclass(frozen=True, slots=True)
class GoldenEvaluation:
    """Outcome of running a golden: accuracy and per-case matches."""

    concept_key: str
    accuracy: float
    passed: bool
    matches: tuple[bool, ...]
    detail: tuple[str, ...] = field(default_factory=tuple)


class ExtractionGoldenInvalid(ValueError):
    """An extraction golden document failed structural validation."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"extraction_golden_invalid: {reason}")


def parse_extraction_goldens(
    data: Mapping[str, object],
) -> Mapping[str, ExtractionGolden]:
    if data.get("contract_version") not in {"1", "2", "3"}:
        raise ExtractionGoldenInvalid("contract_version")
    registry_version = data.get("registry_version")
    if registry_version not in {
        "extraction-goldens-v1",
        "extraction-goldens-v2",
        "extraction-goldens-v3",
    }:
        raise ExtractionGoldenInvalid("registry_version")
    threshold_raw = data.get("threshold")
    threshold_map: Mapping[str, object] = (
        threshold_raw if isinstance(threshold_raw, Mapping) else {}
    )
    default_threshold = _as_float(threshold_map.get("accuracy"), 1.0)
    raw_goldens = data.get("goldens")
    if not isinstance(raw_goldens, list):
        raise ExtractionGoldenInvalid("goldens")
    parsed: dict[str, ExtractionGolden] = {}
    for raw in raw_goldens:
        if not isinstance(raw, Mapping):
            raise ExtractionGoldenInvalid("golden")
        concept_key = raw.get("concept_key")
        source = raw.get("source")
        if not isinstance(concept_key, str) or not concept_key:
            raise ExtractionGoldenInvalid("golden.concept_key")
        if source not in {"rule", "model", "urban"}:
            raise ExtractionGoldenInvalid("golden.source")
        if concept_key in parsed:
            raise ExtractionGoldenInvalid("golden.duplicate")
        raw_cases = raw.get("cases")
        if not isinstance(raw_cases, list) or not raw_cases:
            raise ExtractionGoldenInvalid("golden.cases")
        cases: list[ExtractionGoldenCase] = []
        for case in raw_cases:
            if not isinstance(case, Mapping):
                raise ExtractionGoldenInvalid("golden.case")
            case_input = case.get("input")
            if not isinstance(case_input, Mapping) or not case_input:
                raise ExtractionGoldenInvalid("golden.case.input")
            cases.append(
                ExtractionGoldenCase(
                    input=dict(case_input), expected=case.get("expected")
                )
            )
        parsed[concept_key] = ExtractionGolden(
            concept_key=concept_key,
            source=str(source),
            accuracy_threshold=default_threshold,
            cases=tuple(cases),
        )
    return parsed


def evaluate_extraction_golden(
    golden: ExtractionGolden,
    extract: Callable[[Mapping[str, object]], object],
) -> GoldenEvaluation:
    """Run one golden against an extractor callable and compute accuracy.

    ``extract`` receives the case input projection and returns the observed
    value; the expected value is either a plain value (compared with ``==``)
    or a ``{"min": n}`` constraint (numeric, used by urban counts).
    """
    matches: list[bool] = []
    detail: list[str] = []
    for case in golden.cases:
        try:
            predicted = extract(case.input)
        except Exception as exc:  # noqa: BLE001 - any failure is a mismatch
            matches.append(False)
            detail.append(f"error: {type(exc).__name__}")
            continue
        matched = _matches_expected(predicted, case.expected)
        matches.append(matched)
        if not matched:
            detail.append(
                f"expected={case.expected!r} got={predicted!r}"
            )
    accuracy = sum(matches) / len(matches)
    return GoldenEvaluation(
        concept_key=golden.concept_key,
        accuracy=round(accuracy, 4),
        passed=golden.is_sufficient(accuracy),
        matches=tuple(matches),
        detail=tuple(detail),
    )


def _matches_expected(predicted: object, expected: object) -> bool:
    if isinstance(expected, Mapping) and "min" in expected:
        raw_min = expected.get("min")
        if not isinstance(raw_min, (int, float)) or isinstance(raw_min, bool):
            return False
        minimum = float(raw_min)
        raw_number = predicted
        number = (
            float(raw_number)
            if isinstance(raw_number, (int, float)) and not isinstance(raw_number, bool)
            else None
        )
        return number is not None and number >= minimum
    return predicted == expected


def _as_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default
