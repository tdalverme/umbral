"""Safe, deterministic JSON and Markdown projections for V5 eval evidence."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence

from umbral.application.agent_evals.v4.contracts import (
    ComparisonEvidenceV4,
    ComparisonTrialV4,
    TurnEvidenceV4,
)

_REDACTED_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "access_token",
        "refresh_token",
        "secret",
        "cookie",
        "password",
    }
)
_MAX_ITEMS = 8
_MAX_DEPTH = 3


def report_to_dict_v4(comparison: ComparisonEvidenceV4) -> dict[str, object]:
    """Return a deterministic, JSON-safe and redacted comparison projection."""
    return {
        "baseline": _run_summary(comparison.baseline),
        "candidate": _run_summary(comparison.candidate),
        "review_items": _review_items(comparison.candidate),
    }


def render_markdown_v4(comparison: ComparisonEvidenceV4) -> str:
    """Render a deterministic Markdown view of the bounded review evidence."""
    report = report_to_dict_v4(comparison)
    candidate = report["candidate"]
    review_items = report["review_items"]
    assert isinstance(candidate, dict)
    assert isinstance(review_items, list)
    lines = [
        "# Agent Evals v4",
        "",
        f"- Candidate trials: {candidate['trials']}",
        "- Candidate failures by stage: "
        + json.dumps(
            candidate["failures_by_stage"], ensure_ascii=False, sort_keys=True
        ),
        "",
        "## Representative stage evidence",
        "",
    ]
    if not review_items:
        lines.append("No candidate failure samples.")
    for item in review_items:
        assert isinstance(item, dict)
        lines.extend(
            (
                f"### {item['family']} — {item['failure_stage']} "
                f"({item['reason_code']})",
                "",
                "```json",
                json.dumps(
                    item["sample"], ensure_ascii=False, sort_keys=True, indent=2
                ),
                "```",
                "",
            )
        )
    return "\n".join(lines)


def _run_summary(trials: tuple[ComparisonTrialV4, ...]) -> dict[str, object]:
    failures = Counter(
        trial.result.failure_stage
        for trial in trials
        if trial.result.failure_stage is not None
    )
    return {
        "trials": len(trials),
        "failures_by_stage": {
            stage: failures[stage] for stage in sorted(failures) if stage is not None
        },
    }


def _review_items(trials: tuple[ComparisonTrialV4, ...]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for trial in trials:
        stage = trial.result.failure_stage
        if stage is None:
            continue
        turn = _failure_turn(trial.result.evidence.turns, stage)
        for reason_code in turn.reason_codes:
            key = (trial.family, stage, reason_code)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "family": trial.family,
                    "failure_stage": stage,
                    "reason_code": reason_code,
                    "sample": _sample(trial, turn),
                }
            )
    return items


def _failure_turn(
    turns: tuple[TurnEvidenceV4, ...], stage: str
) -> TurnEvidenceV4:
    return next(turn for turn in turns if turn.failure_stage == stage)


def _sample(trial: ComparisonTrialV4, turn: TurnEvidenceV4) -> dict[str, object]:
    return {
        "case_id": trial.result.evidence.case_id,
        "trial_index": trial.result.evidence.trial_index,
        "failure_kind": trial.result.failure_kind,
        "reason_codes": list(turn.reason_codes),
        "stage_evidence": {
            "schema_valid": turn.schema_valid,
            "authorized_context": _bounded(turn.authorized_context),
            "interpretation": _bounded(turn.interpretation),
            "policy_input": _bounded(turn.policy_input),
            "plan": _bounded(turn.plan),
            "effects": _bounded(turn.effects),
            "state_before": _bounded(turn.state_before),
            "state_after": _bounded(turn.state_after),
        },
    }


def _bounded(value: object, depth: int = 0) -> object:
    if depth >= _MAX_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key in sorted(value, key=str)[:_MAX_ITEMS]:
            rendered_key = str(key)
            normalized_key = rendered_key.casefold()
            if normalized_key in _REDACTED_KEYS:
                result[rendered_key] = "[REDACTED]"
            elif _is_untrusted_listing_key(normalized_key):
                result[rendered_key] = "[OMITTED]"
            else:
                result[rendered_key] = _bounded(value[key], depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_bounded(item, depth + 1) for item in value[:_MAX_ITEMS]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return "[UNSUPPORTED]"


def _is_untrusted_listing_key(key: str) -> bool:
    return key in {"listing", "listings"} or (
        "listing" in key
        and any(
            token in key
            for token in ("body", "raw", "description", "text", "content")
        )
    )
